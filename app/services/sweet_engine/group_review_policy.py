from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.sweet_engine.document_registry import (
    document_family,
    normalize_document_type,
)


@dataclass(frozen=True)
class GroupReviewResult:
    review_required: bool
    review_flags: list[str] = field(default_factory=list)
    positive_signals: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PrintedSequenceResult:
    has_numbering: bool
    complete: bool
    total_pages: int | None
    problem: str = ""


class GroupReviewPolicy:
    """
    Review the completed document group.

    IdentityResolver and BoundaryResolver uncertainty is diagnostic only.
    It does not automatically cause manual review.
    """

    CONTINUATION_TYPES = {
        "BILL_CONTINUATION",
        "AUTHORIZATION_CONTINUATION",
        "FORM_CONTINUATION",
        "DISCHARGE_SUMMARY_CONTINUATION",
        "DOCUMENT_CONTINUATION",
        "CONTINUATION",
    }

    INCOMPATIBLE_FAMILY_PAIRS = {
        frozenset({"IDENTITY", "BILL"}),
        frozenset({"IDENTITY", "PAYMENT"}),
        frozenset({"IDENTITY", "AUTHORIZATION"}),
        frozenset({"IDENTITY", "PREAUTHORIZATION"}),
        frozenset({"IDENTITY", "DISCHARGE_SUMMARY"}),
        frozenset({"IDENTITY", "CLINICAL_ORDER"}),
        frozenset({"IDENTITY", "CLINICAL_RECORD"}),

        frozenset({"PAYMENT", "INVESTIGATION"}),
        frozenset({"PAYMENT", "DISCHARGE_SUMMARY"}),
        frozenset({"PAYMENT", "CLINICAL_ORDER"}),

        frozenset({"BILL", "DISCHARGE_SUMMARY"}),
        frozenset({"BILL", "CLINICAL_ORDER"}),
    }

    def evaluate(
        self,
        *,
        document_type: str,
        page_numbers: list[int],
        pages: list[Any],
    ) -> GroupReviewResult:
        review_flags: list[str] = []
        positive_signals: list[str] = []

        final_type = normalize_document_type(document_type)

        if final_type == "UNKNOWN":
            review_flags.append(
                "Group document type remains UNKNOWN."
            )

        if not self._is_contiguous(page_numbers):
            review_flags.append(
                "Group pages are not contiguous."
            )

        page_types = [
            normalize_document_type(self._page_type(page))
            for page in pages
        ]

        families = {
            document_family(page_type)
            for page_type in page_types
            if page_type != "UNKNOWN"
        }

        for left, right in self._incompatible_pairs(families):
            review_flags.append(
                "Group contains incompatible document families: "
                f"{left} and {right}."
            )

        sequence = self._printed_sequence(pages)

        if sequence.has_numbering:
            if sequence.complete:
                positive_signals.append(
                    "Complete printed page sequence "
                    f"1-{sequence.total_pages} of "
                    f"{sequence.total_pages}."
                )
            else:
                review_flags.append(sequence.problem)

        explicit_starts = [
            self._page_number(page)
            for page in pages
            if self._bool_feature(
                page,
                "explicitDocumentStart",
            )
        ]

        if len(explicit_starts) > 1 and not sequence.complete:
            review_flags.append(
                "Multiple explicit document starts occur inside "
                f"the group at pages {explicit_starts}."
            )

        if page_types:
            first_type = page_types[0]

            if first_type in self.CONTINUATION_TYPES:
                review_flags.append(
                    "Group begins with continuation type "
                    f"{first_type} without an anchor page."
                )

        if final_type in self.CONTINUATION_TYPES:
            review_flags.append(
                f"Final group type {final_type} is a continuation "
                "type rather than a complete document."
            )

        review_flags.extend(
            self._identifier_conflicts(pages)
        )

        if self._has_explicit_start_and_end(pages):
            positive_signals.append(
                "Group contains an explicit document start "
                "and explicit document end."
            )

        if self._has_compatible_anchor(
            pages,
            final_type,
        ):
            positive_signals.append(
                f"Group has a compatible {final_type} anchor."
            )

        return GroupReviewResult(
            review_required=bool(review_flags),
            review_flags=list(
                dict.fromkeys(review_flags)
            ),
            positive_signals=list(
                dict.fromkeys(positive_signals)
            ),
        )

    def _printed_sequence(
        self,
        pages: list[Any],
    ) -> PrintedSequenceResult:
        numbered: list[tuple[int, int, int]] = []

        for page in pages:
            printed = self._int_feature(
                page,
                "printedPageNumber",
            )
            total = self._int_feature(
                page,
                "printedTotalPages",
            )

            if printed is not None and total is not None:
                numbered.append(
                    (
                        self._page_number(page),
                        printed,
                        total,
                    )
                )

        if not numbered:
            return PrintedSequenceResult(
                has_numbering=False,
                complete=False,
                total_pages=None,
            )

        totals = {
            total
            for _, _, total in numbered
        }

        if len(totals) != 1:
            return PrintedSequenceResult(
                has_numbering=True,
                complete=False,
                total_pages=None,
                problem=(
                    "Conflicting printed total-page values "
                    "occur inside the group."
                ),
            )

        total_pages = next(iter(totals))

        printed_numbers = [
            printed
            for _, printed, _ in numbered
        ]

        if len(set(printed_numbers)) != len(
            printed_numbers
        ):
            return PrintedSequenceResult(
                has_numbering=True,
                complete=False,
                total_pages=total_pages,
                problem=(
                    "Duplicate printed page numbers occur "
                    "inside the group."
                ),
            )

        expected = list(
            range(1, total_pages + 1)
        )

        if printed_numbers == expected:
            return PrintedSequenceResult(
                has_numbering=True,
                complete=True,
                total_pages=total_pages,
            )

        missing = sorted(
            set(expected) - set(printed_numbers)
        )

        problem = (
            "Printed page sequence is incomplete "
            "or out of order."
        )

        if missing:
            problem += f" Missing printed pages: {missing}."

        return PrintedSequenceResult(
            has_numbering=True,
            complete=False,
            total_pages=total_pages,
            problem=problem,
        )

    def _identifier_conflicts(
        self,
        pages: list[Any],
    ) -> list[str]:
        flags: list[str] = []

        for key, label in (
            ("billNumber", "bill number"),
            (
                "authorizationNumber",
                "authorization number",
            ),
        ):
            values = {
                self._normalize_identifier(
                    self._feature(page, key)
                )
                for page in pages
                if self._normalize_identifier(
                    self._feature(page, key)
                )
            }

            if len(values) > 1:
                flags.append(
                    f"Conflicting {label} values occur "
                    f"inside the group: {sorted(values)}."
                )

        return flags

    def _has_explicit_start_and_end(
        self,
        pages: list[Any],
    ) -> bool:
        return bool(
            pages
            and self._bool_feature(
                pages[0],
                "explicitDocumentStart",
            )
            and self._bool_feature(
                pages[-1],
                "explicitDocumentEnd",
            )
        )

    def _has_compatible_anchor(
        self,
        pages: list[Any],
        final_type: str,
    ) -> bool:
        if not pages:
            return False

        first_type = normalize_document_type(
            self._page_type(pages[0])
        )

        return (
            first_type == final_type
            or (
                first_type != "UNKNOWN"
                and first_type
                not in self.CONTINUATION_TYPES
                and document_family(first_type)
                == document_family(final_type)
            )
        )

    def _incompatible_pairs(
        self,
        families: set[str],
    ) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        ordered = sorted(families)

        for index, left in enumerate(ordered):
            for right in ordered[index + 1:]:
                pair = frozenset({left, right})

                if pair in self.INCOMPATIBLE_FAMILY_PAIRS:
                    result.append((left, right))

        return result

    @staticmethod
    def _is_contiguous(
        page_numbers: list[int],
    ) -> bool:
        return bool(page_numbers) and (
            page_numbers
            == list(
                range(
                    page_numbers[0],
                    page_numbers[-1] + 1,
                )
            )
        )

    @classmethod
    def _feature(
        cls,
        page: Any,
        key: str,
    ) -> Any:
        candidates = [
            key,
            cls._camel_to_snake(key),
        ]

        for candidate in candidates:
            value = getattr(page, candidate, None)

            if value not in (None, ""):
                return value

        evidence = getattr(page, "evidence", None)
        custom_features = getattr(
            evidence,
            "custom_features",
            None,
        )

        if isinstance(custom_features, dict):
            for candidate in candidates:
                if candidate in custom_features:
                    return custom_features[candidate]

            vision = (
                custom_features.get("vision")
                or custom_features.get(
                    "visionEvidence"
                )
            )

            if isinstance(vision, dict):
                for candidate in candidates:
                    if candidate in vision:
                        return vision[candidate]

        raw = getattr(page, "raw", None)

        if isinstance(raw, dict):
            for candidate in candidates:
                if candidate in raw:
                    return raw[candidate]

        return None

    @classmethod
    def _bool_feature(
        cls,
        page: Any,
        key: str,
    ) -> bool:
        value = cls._feature(page, key)

        if isinstance(value, bool):
            return value

        return str(value or "").strip().lower() in {
            "true",
            "1",
            "yes",
            "y",
        }

    @classmethod
    def _int_feature(
        cls,
        page: Any,
        key: str,
    ) -> int | None:
        value = cls._feature(page, key)

        if value in (None, ""):
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _page_type(page: Any) -> str:
        return str(
            getattr(
                page,
                "final_document_type",
                None,
            )
            or getattr(
                page,
                "document_type",
                None,
            )
            or "UNKNOWN"
        )

    @staticmethod
    def _page_number(page: Any) -> int:
        return int(
            getattr(page, "page_number")
        )

    @staticmethod
    def _normalize_identifier(
        value: Any,
    ) -> str:
        return "".join(
            character
            for character
            in str(value or "").upper()
            if character.isalnum()
        )

    @staticmethod
    def _camel_to_snake(value: str) -> str:
        result: list[str] = []

        for character in value:
            if character.isupper():
                result.append("_")
                result.append(
                    character.lower()
                )
            else:
                result.append(character)

        return "".join(result)