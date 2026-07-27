# app/services/sweet_engine/document_group_resolver.py

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable

from app.services.sweet_engine.boundary_reasoner import (
    BoundaryDecision,
    BoundaryType,
)
from app.services.sweet_engine.boundary_resolver import BoundaryResolver
from app.services.sweet_engine.document_identity_resolver import (
    DocumentIdentityDecision,
    DocumentIdentityResolver,
    IdentityRelation,
)
from app.services.sweet_engine.models import PageInventoryItem
from app.services.sweet_engine.page_inventory import PageInventory
from app.services.sweet_engine.document_registry import (
    document_family,
    normalize_document_type,
)

from app.services.sweet_engine.group_review_policy import (
    GroupReviewPolicy,
)

from app.services.sweet_engine.safe_continuation_merge import (
    SafeContinuationMerge,
)


class GroupStatus(str, Enum):
    RESOLVED = "RESOLVED"
    REVIEW = "REVIEW"


@dataclass
class GroupPage:
    page_number: int
    document_type: str
    identity_relation: str
    boundary_type: str
    identity_confidence: float
    boundary_confidence: float


@dataclass
class DocumentGroup:
    group_id: str
    document_type: str
    document_family: str
    start_page: int
    end_page: int
    page_numbers: list[int]
    pages: list[GroupPage]
    confidence: float
    status: GroupStatus
    identity_chain_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    review_flags: list[str] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.page_numbers)


@dataclass
class DocumentGroupResolution:
    packet_id: str
    groups: list[DocumentGroup]
    total_pages: int
    grouped_pages: int
    ungrouped_pages: list[int]
    duplicate_pages: list[int]
    integrity_valid: bool


@dataclass
class _MutableGroup:
    page_numbers: list[int]
    identity_chain_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    review_flags: list[str] = field(default_factory=list)


class DocumentGroupResolver:
    """
    Build final logical document groups from:

        Page classification
        + DocumentIdentityResolver
        + BoundaryResolver

    The resolver is deliberately conservative. Strong START decisions
    split groups. Strong continuation evidence merges pages. UNKNOWN
    singleton chains can be absorbed into a previous document when the
    boundary stage identifies them as continuations.
    """

    CONTINUATION_TYPES = {
        "BILL_CONTINUATION",
        "AUTHORIZATION_CONTINUATION",
        "FORM_CONTINUATION",
        "DISCHARGE_SUMMARY_CONTINUATION",
        "DOCUMENT_CONTINUATION",
        "CONTINUATION",
    }

    STANDALONE_TYPES = {
        "COVERING_LETTER",
        "CHECKLIST",
        "GIPSA_DECLARATION",
        "PAYMENT_RECEIPT",
        "PATIENT_ID_PROOF",
        "PROPOSER_ID_PROOF",
    }

    # DOCUMENT_FAMILIES = {
    #     "CASHLESS_AUTHORIZATION_LETTER": "AUTHORIZATION",
    #     "PREAUTHORIZATION_FORM": "PREAUTHORIZATION",
    #     "FINAL_HOSPITAL_BILL": "BILL",
    #     "BILL_CONTINUATION": "BILL",
    #     "PAYMENT_RECEIPT": "PAYMENT",
    #     "TREATMENT_ORDER": "TREATMENT_ORDER",
    #     "DISCHARGE_SUMMARY": "DISCHARGE_SUMMARY",
    #     "PATIENT_ID_PROOF": "PATIENT_ID",
    #     "PROPOSER_ID_PROOF": "PROPOSER_ID",
    #     "CHECKLIST": "CHECKLIST",
    #     "COVERING_LETTER": "COVERING_LETTER",
    #     "GIPSA_DECLARATION": "DECLARATION",
    #     "UNKNOWN": "UNKNOWN",
    # }

    def __init__(
        self,
        *,
        identity_resolver: DocumentIdentityResolver | None = None,
        boundary_resolver: BoundaryResolver | None = None,
        review_policy: GroupReviewPolicy | None = None,
        continuation_merger: SafeContinuationMerge | None = None,
    ) -> None:
        self.identity_resolver = (
            identity_resolver or DocumentIdentityResolver()
        )
        self.boundary_resolver = boundary_resolver or BoundaryResolver()
        self.review_policy = review_policy or GroupReviewPolicy()
        self.continuation_merger = (
            continuation_merger or SafeContinuationMerge()
        )

    def resolve_inventory(
        self,
        inventory: PageInventory,
        *,
        identity_decisions: list[DocumentIdentityDecision] | None = None,
        boundary_decisions: list[BoundaryDecision] | None = None,
    ) -> DocumentGroupResolution:
        pages = sorted(
            inventory.pages,
            key=lambda page: page.page_number,
        )
        page_by_number = {
            page.page_number: page
            for page in pages
        }

        identities = (
            identity_decisions
            if identity_decisions is not None
            else self.identity_resolver.resolve_inventory(inventory)
        )
        boundaries = (
            boundary_decisions
            if boundary_decisions is not None
            else self.boundary_resolver.resolve_inventory(inventory)
        )

        identity_by_page = {
            item.page_number: item
            for item in identities
        }
        boundary_by_page = {
            item.page_number: item
            for item in boundaries
        }

        mutable_groups = self._build_initial_groups(
            pages=pages,
            identity_by_page=identity_by_page,
            boundary_by_page=boundary_by_page,
        )

        # NEW STEP
        mutable_groups = self._apply_safe_sequence_rules(
            groups=mutable_groups,
            page_by_number=page_by_number,
        )

        mutable_groups = self._merge_safe_continuations(
            groups=mutable_groups,
            page_by_number=page_by_number,
        )

        mutable_groups = self._merge_unknown_singletons(
            groups=mutable_groups,
            page_by_number=page_by_number,
            identity_by_page=identity_by_page,
            boundary_by_page=boundary_by_page,
        )

        mutable_groups = self._merge_boundary_continuations(
            groups=mutable_groups,
            page_by_number=page_by_number,
            identity_by_page=identity_by_page,
            boundary_by_page=boundary_by_page,
        )

        final_groups = self._finalize_groups(
            packet_id=str(inventory.packet_id),
            groups=mutable_groups,
            page_by_number=page_by_number,
            identity_by_page=identity_by_page,
            boundary_by_page=boundary_by_page,
        )

        resolution = self._build_resolution(
            packet_id=str(inventory.packet_id),
            total_pages=inventory.total_pages,
            groups=final_groups,
        )

        self._apply_groups_to_inventory(
            page_by_number=page_by_number,
            groups=final_groups,
        )

        return resolution

    def _build_initial_groups(
        self,
        *,
        pages: list[PageInventoryItem],
        identity_by_page: dict[int, DocumentIdentityDecision],
        boundary_by_page: dict[int, BoundaryDecision],
    ) -> list[_MutableGroup]:
        groups: list[_MutableGroup] = []
        current: _MutableGroup | None = None

        for page in pages:
            page_number = page.page_number
            identity = identity_by_page[page_number]
            boundary = boundary_by_page[page_number]

            should_start = current is None

            if current is not None:
                if boundary.boundary_type == BoundaryType.START:
                    should_start = True
                elif (
                    identity.relation == IdentityRelation.NEW_DOCUMENT
                    and boundary.boundary_type
                    != BoundaryType.CONTINUATION
                ):
                    should_start = True

            if should_start:
                current = _MutableGroup(
                    page_numbers=[page_number],
                    identity_chain_ids=self._identity_chain_list(
                        identity.identity_chain_id
                    ),
                    reasons=[
                        self._start_reason(identity, boundary)
                    ],
                )
                groups.append(current)
            else:
                current.page_numbers.append(page_number)
                self._append_unique(
                    current.identity_chain_ids,
                    identity.identity_chain_id,
                )
                current.reasons.append(
                    self._continuation_reason(
                        identity,
                        boundary,
                    )
                )

                if identity.relation == IdentityRelation.UNCERTAIN:
                    current.reasons.append(
                        f"Page {page_number} had uncertain identity "
                        "evidence; final group review policy will "
                        "evaluate the completed group."
                    )

                if boundary.boundary_type == BoundaryType.AMBIGUOUS:
                    current.reasons.append(
                        f"Page {page_number} had ambiguous boundary "
                        "evidence; final group review policy will "
                        "evaluate the completed group."
                    )

        return groups

    def _merge_unknown_singletons(
        self,
        *,
        groups: list[_MutableGroup],
        page_by_number: dict[int, PageInventoryItem],
        identity_by_page: dict[int, DocumentIdentityDecision],
        boundary_by_page: dict[int, BoundaryDecision],
    ) -> list[_MutableGroup]:
        if len(groups) < 2:
            return groups

        result: list[_MutableGroup] = []
        index = 0

        while index < len(groups):
            group = groups[index]

            if (
                len(group.page_numbers) == 1
                and result
            ):
                page_number = group.page_numbers[0]
                page_type = self._page_type(
                    page_by_number[page_number]
                )
                boundary = boundary_by_page[page_number]
                identity = identity_by_page[page_number]
                previous_group = result[-1]

                next_group = (
                    groups[index + 1]
                    if index + 1 < len(groups)
                    else None
                )

                previous_type = self._dominant_type(
                    previous_group.page_numbers,
                    page_by_number,
                )

                next_starts_strongly = False
                if next_group:
                    next_page_number = next_group.page_numbers[0]
                    next_boundary = boundary_by_page[
                        next_page_number
                    ]
                    next_identity = identity_by_page[
                        next_page_number
                    ]
                    next_starts_strongly = (
                        next_boundary.boundary_type
                        == BoundaryType.START
                        or next_identity.relation
                        == IdentityRelation.NEW_DOCUMENT
                    )

                should_merge = (
                    page_type == "UNKNOWN"
                    and previous_type
                    not in self.STANDALONE_TYPES
                    and (
                        boundary.boundary_type
                        in {
                            BoundaryType.CONTINUATION,
                            BoundaryType.AMBIGUOUS,
                        }
                        or identity.relation
                        == IdentityRelation.UNCERTAIN
                        or next_starts_strongly
                    )
                )

                if should_merge:
                    previous_group.page_numbers.extend(
                        group.page_numbers
                    )
                    for chain_id in group.identity_chain_ids:
                        self._append_unique(
                            previous_group.identity_chain_ids,
                            chain_id,
                        )
                    previous_group.reasons.append(
                        f"Merged UNKNOWN singleton page "
                        f"{page_number} into the previous group "
                        "because sequence-level evidence indicates "
                        "a continuation."
                    )
                    previous_group.review_flags.append(
                        f"Page {page_number} was classified UNKNOWN "
                        "and merged using sequence evidence."
                    )
                    index += 1
                    continue

            result.append(group)
            index += 1

        return result

    def _merge_boundary_continuations(
        self,
        *,
        groups: list[_MutableGroup],
        page_by_number: dict[int, PageInventoryItem],
        identity_by_page: dict[int, DocumentIdentityDecision],
        boundary_by_page: dict[int, BoundaryDecision],
    ) -> list[_MutableGroup]:
        if len(groups) < 2:
            return groups

        merged: list[_MutableGroup] = [groups[0]]

        for group in groups[1:]:
            previous = merged[-1]
            first_page_number = group.page_numbers[0]
            boundary = boundary_by_page[first_page_number]
            identity = identity_by_page[first_page_number]

            previous_type = self._dominant_type(
                previous.page_numbers,
                page_by_number,
            )
            current_type = self._dominant_type(
                group.page_numbers,
                page_by_number,
            )

            same_family = (
                self._family(previous_type)
                == self._family(current_type)
            )
            continuation_type = (
                current_type in self.CONTINUATION_TYPES
            )

            should_merge = (
                boundary.boundary_type
                == BoundaryType.CONTINUATION
                and (
                    same_family
                    or continuation_type
                    or current_type == "UNKNOWN"
                )
            )

            if (
                not should_merge
                and identity.relation
                == IdentityRelation.SAME_DOCUMENT
                and same_family
            ):
                should_merge = True

            if should_merge:
                previous.page_numbers.extend(
                    group.page_numbers
                )
                for chain_id in group.identity_chain_ids:
                    self._append_unique(
                        previous.identity_chain_ids,
                        chain_id,
                    )
                previous.reasons.append(
                    f"Merged group beginning at page "
                    f"{first_page_number} using continuation "
                    "evidence."
                )
                previous.review_flags.extend(
                    group.review_flags
                )
            else:
                merged.append(group)

        return merged

    def _finalize_groups(
        self,
        *,
        packet_id: str,
        groups: list[_MutableGroup],
        page_by_number: dict[int, PageInventoryItem],
        identity_by_page: dict[int, DocumentIdentityDecision],
        boundary_by_page: dict[int, BoundaryDecision],
    ) -> list[DocumentGroup]:
        final_groups: list[DocumentGroup] = []

        for index, group in enumerate(groups, start=1):
            page_numbers = sorted(set(group.page_numbers))
            document_type = self._dominant_type(
                page_numbers,
                page_by_number,
            )
            document_family = self._family(document_type)

            page_entries: list[GroupPage] = []
            confidence_values: list[float] = []

            for page_number in page_numbers:
                page = page_by_number[page_number]
                identity = identity_by_page[page_number]
                boundary = boundary_by_page[page_number]

                page_entries.append(
                    GroupPage(
                        page_number=page_number,
                        document_type=self._page_type(page),
                        identity_relation=identity.relation.value,
                        boundary_type=boundary.boundary_type.value,
                        identity_confidence=identity.confidence,
                        boundary_confidence=boundary.confidence,
                    )
                )

                confidence_values.extend(
                    [
                        identity.confidence,
                        boundary.confidence,
                    ]
                )

            confidence = (
                sum(confidence_values)
                / len(confidence_values)
                if confidence_values
                else 0.0
            )

            review_result = self.review_policy.evaluate(
                document_type=document_type,
                page_numbers=page_numbers,
                pages=[
                    page_by_number[number]
                    for number in page_numbers
                ],
            )

            review_flags = list(
                dict.fromkeys(
                    [
                        *group.review_flags,
                        *review_result.review_flags,
                    ]
                )
            )

            group.reasons.extend(
                review_result.positive_signals
            )
            status = (
                GroupStatus.REVIEW
                if review_flags
                else GroupStatus.RESOLVED
            )

            final_groups.append(
                DocumentGroup(
                    group_id=(
                        f"{packet_id}-group-{index:03d}"
                    ),
                    document_type=document_type,
                    document_family=document_family,
                    start_page=page_numbers[0],
                    end_page=page_numbers[-1],
                    page_numbers=page_numbers,
                    pages=page_entries,
                    confidence=round(confidence, 4),
                    status=status,
                    identity_chain_ids=group.identity_chain_ids,
                    reasons=list(dict.fromkeys(group.reasons)),
                    review_flags=review_flags,
                )
            )

        return final_groups

    def _build_resolution(
        self,
        *,
        packet_id: str,
        total_pages: int,
        groups: list[DocumentGroup],
    ) -> DocumentGroupResolution:
        occurrences: Counter[int] = Counter(
            page_number
            for group in groups
            for page_number in group.page_numbers
        )

        expected = set(range(1, total_pages + 1))
        actual = set(occurrences)

        ungrouped = sorted(expected - actual)
        duplicate = sorted(
            page_number
            for page_number, count in occurrences.items()
            if count > 1
        )

        return DocumentGroupResolution(
            packet_id=packet_id,
            groups=groups,
            total_pages=total_pages,
            grouped_pages=len(actual),
            ungrouped_pages=ungrouped,
            duplicate_pages=duplicate,
            integrity_valid=(
                not ungrouped
                and not duplicate
                and len(actual) == total_pages
            ),
        )

    def _apply_safe_sequence_rules(
            self,
            *,
            groups: list[_MutableGroup],
            page_by_number: dict[
                int,
                PageInventoryItem,
            ],
    ) -> list[_MutableGroup]:
        """
        Merge adjacent provisional groups only when strong
        structured sequence evidence proves continuity.
        """

        if len(groups) < 2:
            return groups

        merged: list[_MutableGroup] = [
            groups[0]
        ]

        for current in groups[1:]:
            previous = merged[-1]

            previous_page = page_by_number[
                previous.page_numbers[-1]
            ]

            current_page = page_by_number[
                current.page_numbers[0]
            ]

            if self._safe_sequence_merge(
                    previous_page=previous_page,
                    current_page=current_page,
            ):
                previous.page_numbers.extend(
                    current.page_numbers
                )

                for chain_id in (
                        current.identity_chain_ids
                ):
                    self._append_unique(
                        previous.identity_chain_ids,
                        chain_id,
                    )

                previous.reasons.extend(
                    current.reasons
                )

                previous.reasons.append(
                    "Merged group beginning at page "
                    f"{current.page_numbers[0]} using "
                    "printed-page sequence evidence."
                )
            else:
                merged.append(current)

        return merged

    def _safe_sequence_merge(
            self,
            *,
            previous_page: PageInventoryItem,
            current_page: PageInventoryItem,
    ) -> bool:
        if self._bool_feature(
                current_page,
                "explicitDocumentStart",
        ):
            return False

        previous_type = self._page_type(
            previous_page
        )
        current_type = self._page_type(
            current_page
        )

        previous_family = self._family(
            previous_type
        )
        current_family = self._family(
            current_type
        )

        previous_number = self._int_feature(
            previous_page,
            "printedPageNumber",
        )
        current_number = self._int_feature(
            current_page,
            "printedPageNumber",
        )

        previous_total = self._int_feature(
            previous_page,
            "printedTotalPages",
        )
        current_total = self._int_feature(
            current_page,
            "printedTotalPages",
        )

        is_next_printed_page = (
                previous_number is not None
                and current_number is not None
                and previous_total is not None
                and current_total is not None
                and previous_total == current_total
                and current_number
                == previous_number + 1
        )

        if not is_next_printed_page:
            return False

        compatible_family = (
                previous_family == current_family
                or current_type
                in self.CONTINUATION_TYPES
        )

        return compatible_family

    def _apply_groups_to_inventory(
        self,
        *,
        page_by_number: dict[int, PageInventoryItem],
        groups: list[DocumentGroup],
    ) -> None:
        for group in groups:
            for page_number in group.page_numbers:
                page = page_by_number[page_number]
                page.evidence.custom_features[
                    "documentGroup"
                ] = {
                    "groupId": group.group_id,
                    "documentType": group.document_type,
                    "documentFamily": group.document_family,
                    "startPage": group.start_page,
                    "endPage": group.end_page,
                    "pageNumbers": group.page_numbers,
                    "confidence": group.confidence,
                    "status": group.status.value,
                    "reviewFlags": group.review_flags,
                }

                page.add_processing_note(
                    f"Document group {group.group_id}: "
                    f"{group.document_type}, "
                    f"pages={group.page_numbers}, "
                    f"confidence={group.confidence:.2f}, "
                    f"status={group.status.value}."
                )

    def _dominant_type(
            self,
            page_numbers: Iterable[int],
            page_by_number: dict[
                int,
                PageInventoryItem,
            ],
    ) -> str:
        numbers = list(page_numbers)

        types = [
            self._page_type(
                page_by_number[number]
            )
            for number in numbers
        ]

        # Strongest rule: explicit document start.
        for number, document_type in zip(
                numbers,
                types,
        ):
            page = page_by_number[number]

            if (
                    self._bool_feature(
                        page,
                        "explicitDocumentStart",
                    )
                    and document_type != "UNKNOWN"
                    and document_type
                    not in self.CONTINUATION_TYPES
            ):
                return document_type

        # Otherwise use first recognized anchor.
        for document_type in types:
            if (
                    document_type != "UNKNOWN"
                    and document_type
                    not in self.CONTINUATION_TYPES
            ):
                return document_type

        recognized = [
            document_type
            for document_type in types
            if document_type != "UNKNOWN"
        ]

        if not recognized:
            return "UNKNOWN"

        return Counter(
            recognized
        ).most_common(1)[0][0]
    @staticmethod
    def _page_type(page: PageInventoryItem) -> str:
        value = str(
            page.final_document_type or "UNKNOWN"
        ).strip().upper()
        return value.replace(" ", "_").replace("-", "_")

    @staticmethod
    def _family(document_type: str) -> str:
        return document_family(document_type)

    @staticmethod
    def _is_contiguous(page_numbers: list[int]) -> bool:
        return page_numbers == list(
            range(page_numbers[0], page_numbers[-1] + 1)
        )

    @staticmethod
    def _identity_chain_list(
        identity_chain_id: str | None,
    ) -> list[str]:
        return (
            [identity_chain_id]
            if identity_chain_id
            else []
        )

    @staticmethod
    def _append_unique(
        values: list[str],
        value: str | None,
    ) -> None:
        if value and value not in values:
            values.append(value)

    @staticmethod
    def _start_reason(
        identity: DocumentIdentityDecision,
        boundary: BoundaryDecision,
    ) -> str:
        return (
            f"Started group at page {identity.page_number}: "
            f"identity={identity.relation.value}, "
            f"boundary={boundary.boundary_type.value}."
        )

    @staticmethod
    def _continuation_reason(
        identity: DocumentIdentityDecision,
        boundary: BoundaryDecision,
    ) -> str:
        return (
            f"Attached page {identity.page_number}: "
            f"identity={identity.relation.value}, "
            f"boundary={boundary.boundary_type.value}."
        )

    @classmethod
    def _feature(
            cls,
            page: PageInventoryItem,
            key: str,
    ) -> Any:
        candidates = [
            key,
            cls._camel_to_snake(key),
        ]

        for candidate in candidates:
            value = getattr(
                page,
                candidate,
                None,
            )

            if value not in (None, ""):
                return value

        evidence = getattr(
            page,
            "evidence",
            None,
        )

        custom_features = getattr(
            evidence,
            "custom_features",
            None,
        )

        if isinstance(custom_features, dict):
            for candidate in candidates:
                if candidate in custom_features:
                    return custom_features[
                        candidate
                    ]

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

        return None

    @classmethod
    def _bool_feature(
            cls,
            page: PageInventoryItem,
            key: str,
    ) -> bool:
        value = cls._feature(page, key)

        if isinstance(value, bool):
            return value

        return str(value or "").lower() in {
            "true",
            "1",
            "yes",
            "y",
        }

    @classmethod
    def _int_feature(
            cls,
            page: PageInventoryItem,
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
    def _camel_to_snake(
            value: str,
    ) -> str:
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

    def _merge_safe_continuations(
        self,
        *,
        groups: list[_MutableGroup],
        page_by_number: dict[int, PageInventoryItem],
    ) -> list[_MutableGroup]:
        if len(groups) < 2:
            return groups

        merged: list[_MutableGroup] = [groups[0]]

        for current in groups[1:]:
            previous = merged[-1]

            previous_type = self._dominant_type(
                previous.page_numbers,
                page_by_number,
            )
            current_type = self._dominant_type(
                current.page_numbers,
                page_by_number,
            )

            decision = self.continuation_merger.decide(
                previous_pages=[
                    page_by_number[number]
                    for number in previous.page_numbers
                ],
                current_pages=[
                    page_by_number[number]
                    for number in current.page_numbers
                ],
                previous_document_type=previous_type,
                current_document_type=current_type,
            )

            if not decision.should_merge:
                current.reasons.append(
                    "SafeContinuationMerge rejected attachment "
                    f"to {previous_type}: "
                    + " | ".join(decision.reasons)
                )

                merged.append(current)
                continue

            previous.page_numbers.extend(current.page_numbers)

            for chain_id in current.identity_chain_ids:
                self._append_unique(
                    previous.identity_chain_ids,
                    chain_id,
                )

            previous.reasons.extend(current.reasons)
            previous.reasons.append(
                "SafeContinuationMerge attached pages "
                f"{current.page_numbers} to {previous_type}; "
                f"confidence={decision.confidence:.2f}; "
                f"evidence={' | '.join(decision.reasons)}"
            )

            # Do not copy continuation-without-anchor review flags.
            # The continuation now has a valid anchor. Any other material
            # group problems will be recalculated by GroupReviewPolicy.

        return merged



__all__ = [
    "DocumentGroup",
    "DocumentGroupResolution",
    "DocumentGroupResolver",
    "GroupPage",
    "GroupStatus",
]
