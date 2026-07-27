# app/services/sweet_engine_v2/document_bucket_resolver.py

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.services.sweet_engine.document_group_resolver import (
    DocumentGroup,
    DocumentGroupResolution,
    GroupPage,
    GroupStatus,
)
from app.services.sweet_engine.models import PageInventoryItem
from app.services.sweet_engine.page_inventory import PageInventory

from app.services.sweet_engine_v2.claim_document_catalog import (
    can_continue,
    compatible_bucket_types,
    definition_for,
    document_family,
    hard_separation,
    is_continuation,
    is_standalone,
    normalize_document_type,
)


class BucketStatus(str, Enum):
    RESOLVED = "RESOLVED"
    REVIEW = "REVIEW"


@dataclass
class BucketReviewItem:
    code: str
    message: str
    suggested_action: str
    page_numbers: list[int] = field(default_factory=list)


@dataclass
class DocumentBucket:
    bucket_id: str
    document_type: str
    document_family: str
    pages: list[PageInventoryItem] = field(default_factory=list)
    score_reasons: list[str] = field(default_factory=list)
    review_items: list[BucketReviewItem] = field(default_factory=list)
    status: BucketStatus = BucketStatus.RESOLVED

    @property
    def page_numbers(self) -> list[int]:
        return [page.page_number for page in self.pages]

    @property
    def first_page_number(self) -> int:
        return self.pages[0].page_number

    @property
    def last_page_number(self) -> int:
        return self.pages[-1].page_number


@dataclass(frozen=True)
class BucketCandidateScore:
    bucket_id: str
    score: int
    strong_signals: int
    reasons: tuple[str, ...]
    rejected: bool = False
    rejection_reason: str = ""


class DocumentBucketResolver:
    """
    Conservative V2 logical-document grouping.

    Core safety rules:
      * Classification type is evaluated before adjacency.
      * Different canonical types do not merge merely because they share a
        patient, claim, date, payer, or document family.
      * Continuation pages can join only declared parent document types.
      * Standalone and identity-role documents remain isolated.
      * A low-confidence decision starts a separate REVIEW bucket rather than
        creating a silent cross-type merge.

    The output intentionally reuses the legacy DocumentGroupResolution model,
    allowing PhysicalDocumentBuilder to remain unchanged.
    """

    MIN_SAME_TYPE_SCORE = 55
    MIN_CONTINUATION_SCORE = 45
    MIN_NON_ADJACENT_SCORE = 95
    MAX_BACKTRACK_BUCKETS = 8

    def resolve_inventory(
        self,
        inventory: PageInventory,
    ) -> DocumentGroupResolution:
        pages = sorted(inventory.pages, key=lambda item: item.page_number)
        buckets: list[DocumentBucket] = []

        for page in pages:
            self._assign_page(page=page, buckets=buckets)

        self._validate_buckets(buckets)
        groups = self._to_document_groups(
            packet_id=str(inventory.packet_id),
            buckets=buckets,
        )
        resolution = self._build_resolution(
            packet_id=str(inventory.packet_id),
            total_pages=inventory.total_pages,
            groups=groups,
        )
        self._apply_group_ids(buckets)
        return resolution

    def _assign_page(
        self,
        *,
        page: PageInventoryItem,
        buckets: list[DocumentBucket],
    ) -> None:
        page_type = normalize_document_type(page.final_document_type)
        page.final_document_type = page_type

        if not buckets:
            buckets.append(self._new_bucket(page, len(buckets) + 1))
            return

        # Strict standalone policy prevents patient/proposer IDs, receipts,
        # cards and other one-page documents from being accidentally combined.
        if is_standalone(page_type):
            buckets.append(self._new_bucket(page, len(buckets) + 1))
            return

        compatible = set(compatible_bucket_types(page_type))
        candidate_buckets: list[DocumentBucket] = []

        for bucket in reversed(buckets[-self.MAX_BACKTRACK_BUCKETS:]):
            if bucket.document_type not in compatible:
                continue

            if hard_separation(bucket.document_type, page_type):
                continue

            candidate_buckets.append(bucket)

        if not candidate_buckets:
            bucket = self._new_bucket(page, len(buckets) + 1)

            if is_continuation(page_type):
                bucket.status = BucketStatus.REVIEW
                bucket.review_items.append(
                    BucketReviewItem(
                        code="CONTINUATION_WITHOUT_PARENT",
                        page_numbers=[page.page_number],
                        message=(
                            f"Page {page.page_number} was identified as "
                            f"{page_type.replace('_', ' ').title()}, but no "
                            "compatible parent document was found."
                        ),
                        suggested_action=(
                            "Select the correct parent document or keep this "
                            "page as a separate reviewed document."
                        ),
                    )
                )

            buckets.append(bucket)
            return

        scored = [
            self._score_page_for_bucket(page=page, bucket=bucket)
            for bucket in candidate_buckets
        ]
        eligible = [
            item
            for item in scored
            if not item.rejected
        ]

        if not eligible:
            buckets.append(self._new_bucket(page, len(buckets) + 1))
            return

        eligible.sort(
            key=lambda item: (
                item.score,
                item.strong_signals,
                self._bucket_by_id(buckets, item.bucket_id).last_page_number,
            ),
            reverse=True,
        )
        best = eligible[0]
        best_bucket = self._bucket_by_id(buckets, best.bucket_id)

        threshold = (
            self.MIN_CONTINUATION_SCORE
            if is_continuation(page_type)
            else self.MIN_SAME_TYPE_SCORE
        )

        is_adjacent = best_bucket.last_page_number + 1 == page.page_number

        if not is_adjacent:
            threshold = max(threshold, self.MIN_NON_ADJACENT_SCORE)

        if best.score < threshold:
            new_bucket = self._new_bucket(page, len(buckets) + 1)

            if is_continuation(page_type):
                new_bucket.status = BucketStatus.REVIEW
                new_bucket.review_items.append(
                    BucketReviewItem(
                        code="CONTINUATION_PARENT_UNCERTAIN",
                        page_numbers=[page.page_number],
                        message=(
                            f"Page {page.page_number} appears to be a "
                            f"{page_type.replace('_', ' ').title()}, but the "
                            f"best parent candidate scored only {best.score}; "
                            f"the safe threshold is {threshold}."
                        ),
                        suggested_action=(
                            f"Review whether page {page.page_number} belongs "
                            f"with pages {best_bucket.page_numbers}."
                        ),
                    )
                )

            buckets.append(new_bucket)
            return

        self._append_page(
            bucket=best_bucket,
            page=page,
            score=best.score,
            reasons=list(best.reasons),
        )

    def _score_page_for_bucket(
        self,
        *,
        page: PageInventoryItem,
        bucket: DocumentBucket,
    ) -> BucketCandidateScore:
        page_type = normalize_document_type(page.final_document_type)
        bucket_type = bucket.document_type
        reasons: list[str] = []
        score = 0
        strong = 0

        if hard_separation(bucket_type, page_type):
            return BucketCandidateScore(
                bucket_id=bucket.bucket_id,
                score=-1000,
                strong_signals=0,
                reasons=(),
                rejected=True,
                rejection_reason="Catalog hard-separation rule.",
            )

        if is_continuation(page_type):
            if not can_continue(bucket_type, page_type):
                return BucketCandidateScore(
                    bucket_id=bucket.bucket_id,
                    score=-1000,
                    strong_signals=0,
                    reasons=(),
                    rejected=True,
                    rejection_reason=(
                        f"{page_type} cannot continue {bucket_type}."
                    ),
                )
            score += 40
            strong += 1
            reasons.append(
                f"Continuation type {page_type} is declared compatible "
                f"with parent type {bucket_type}."
            )
        elif page_type == bucket_type:
            score += 35
            reasons.append("Canonical document type matches the bucket.")
        else:
            return BucketCandidateScore(
                bucket_id=bucket.bucket_id,
                score=-1000,
                strong_signals=0,
                reasons=(),
                rejected=True,
                rejection_reason="Canonical document types differ.",
            )

        previous = bucket.pages[-1]
        adjacent = previous.page_number + 1 == page.page_number

        if adjacent:
            score += 15
            reasons.append("Page is physically adjacent to the bucket.")
        else:
            score -= 20
            reasons.append("Page is not adjacent; stronger evidence is required.")

        previous_printed = self._int_feature(previous, "printedPageNumber")
        current_printed = self._int_feature(page, "printedPageNumber")
        previous_total = self._int_feature(previous, "printedTotalPages")
        current_total = self._int_feature(page, "printedTotalPages")

        if (
            previous_printed is not None
            and current_printed is not None
            and current_printed == previous_printed + 1
            and (
                previous_total is None
                or current_total is None
                or previous_total == current_total
            )
        ):
            score += 70
            strong += 1
            reasons.append("Printed page numbers continue sequentially.")

        for key, label, weight in (
            ("authorizationNumber", "authorization number", 60),
            ("billNumber", "bill number", 60),
            ("claimNumber", "claim number", 35),
            ("mrn", "MRN", 35),
            ("ipNumber", "IP number", 35),
            ("reportNumber", "report number", 60),
            ("accessionNumber", "accession number", 60),
        ):
            page_value = self._normalise_identifier(self._feature(page, key))
            bucket_values = {
                self._normalise_identifier(self._feature(item, key))
                for item in bucket.pages
                if self._normalise_identifier(self._feature(item, key))
            }

            if page_value and page_value in bucket_values:
                score += weight
                strong += 1
                reasons.append(f"Matching {label}.")
            elif page_value and bucket_values and page_value not in bucket_values:
                return BucketCandidateScore(
                    bucket_id=bucket.bucket_id,
                    score=-1000,
                    strong_signals=strong,
                    reasons=tuple(reasons),
                    rejected=True,
                    rejection_reason=f"Conflicting {label}.",
                )

        for key, label, weight in (
            ("patientName", "patient name", 10),
            ("payerName", "payer", 8),
            ("templateSignature", "template", 18),
            ("headerSignature", "header", 15),
            ("documentDate", "document date", 8),
        ):
            page_value = self._normalise_identifier(self._feature(page, key))
            bucket_values = {
                self._normalise_identifier(self._feature(item, key))
                for item in bucket.pages
                if self._normalise_identifier(self._feature(item, key))
            }

            if page_value and page_value in bucket_values:
                score += weight
                reasons.append(f"Matching {label}.")

        page_role = str(self._feature(page, "pageRole") or "").upper()

        if page_role in {"CONTINUATION", "END"}:
            score += 15
            reasons.append(f"Vision page role is {page_role}.")

        if self._bool_feature(page, "explicitDocumentStart"):
            score -= 80
            reasons.append("Page explicitly declares a new document start.")

        return BucketCandidateScore(
            bucket_id=bucket.bucket_id,
            score=score,
            strong_signals=strong,
            reasons=tuple(reasons),
        )

    def _new_bucket(
        self,
        page: PageInventoryItem,
        sequence: int,
    ) -> DocumentBucket:
        page_type = normalize_document_type(page.final_document_type)
        status = (
            BucketStatus.REVIEW
            if page_type == "UNKNOWN" or page.requires_review
            else BucketStatus.RESOLVED
        )

        bucket = DocumentBucket(
            bucket_id=f"bucket-{sequence:03d}",
            document_type=page_type,
            document_family=document_family(page_type),
            pages=[page],
            status=status,
        )

        if page_type == "UNKNOWN":
            bucket.review_items.append(
                BucketReviewItem(
                    code="UNKNOWN_DOCUMENT",
                    page_numbers=[page.page_number],
                    message=(
                        f"Page {page.page_number} could not be assigned a "
                        "reliable document type."
                    ),
                    suggested_action=(
                        "Select the correct document type before completing "
                        "the claim checklist."
                    ),
                )
            )

        return bucket

    @staticmethod
    def _append_page(
        *,
        bucket: DocumentBucket,
        page: PageInventoryItem,
        score: int,
        reasons: list[str],
    ) -> None:
        bucket.pages.append(page)
        bucket.score_reasons.append(
            f"Page {page.page_number} joined with score {score}: "
            + " | ".join(reasons)
        )

    def _validate_buckets(
        self,
        buckets: list[DocumentBucket],
    ) -> None:
        for bucket in buckets:
            page_numbers = bucket.page_numbers

            if page_numbers != list(
                range(page_numbers[0], page_numbers[-1] + 1)
            ):
                bucket.status = BucketStatus.REVIEW
                bucket.review_items.append(
                    BucketReviewItem(
                        code="NON_CONTIGUOUS_BUCKET",
                        page_numbers=page_numbers,
                        message=(
                            f"{definition_for(bucket.document_type).display_name} "
                            f"contains non-contiguous source pages {page_numbers}."
                        ),
                        suggested_action=(
                            "Verify whether these pages are one document or "
                            "should be separated into multiple documents."
                        ),
                    )
                )

            first_type = normalize_document_type(
                bucket.pages[0].final_document_type
            )

            if is_continuation(first_type):
                bucket.status = BucketStatus.REVIEW

            # Multiple explicit starts inside one bucket imply that pages may
            # actually represent separate document instances.
            starts = [
                page.page_number
                for page in bucket.pages
                if self._bool_feature(page, "explicitDocumentStart")
            ]

            if len(starts) > 1:
                bucket.status = BucketStatus.REVIEW
                bucket.review_items.append(
                    BucketReviewItem(
                        code="MULTIPLE_DOCUMENT_STARTS",
                        page_numbers=starts,
                        message=(
                            "More than one explicit document start was found "
                            f"inside this group at pages {starts}."
                        ),
                        suggested_action=(
                            "Split this group at the appropriate start page."
                        ),
                    )
                )

    def _to_document_groups(
        self,
        *,
        packet_id: str,
        buckets: list[DocumentBucket],
    ) -> list[DocumentGroup]:
        groups: list[DocumentGroup] = []

        for sequence, bucket in enumerate(buckets, start=1):
            confidences = [
                float(page.confidence or 0.0)
                for page in bucket.pages
            ]
            confidence = (
                round(sum(confidences) / len(confidences), 4)
                if confidences
                else 0.0
            )

            review_flags = [
                item.message
                for item in bucket.review_items
            ]

            group_pages = [
                GroupPage(
                    page_number=page.page_number,
                    document_type=normalize_document_type(
                        page.final_document_type
                    ),
                    identity_relation="BUCKET_ASSIGNMENT",
                    boundary_type=str(
                        getattr(page.boundary_type, "value", page.boundary_type)
                    ),
                    identity_confidence=float(page.confidence or 0.0),
                    boundary_confidence=float(page.confidence or 0.0),
                )
                for page in bucket.pages
            ]

            groups.append(
                DocumentGroup(
                    group_id=f"{packet_id}-bucket-{sequence:03d}",
                    document_type=bucket.document_type,
                    document_family=bucket.document_family,
                    start_page=bucket.first_page_number,
                    end_page=bucket.last_page_number,
                    page_numbers=bucket.page_numbers,
                    pages=group_pages,
                    confidence=confidence,
                    status=(
                        GroupStatus.REVIEW
                        if bucket.status == BucketStatus.REVIEW
                        else GroupStatus.RESOLVED
                    ),
                    identity_chain_ids=[],
                    reasons=list(bucket.score_reasons),
                    review_flags=review_flags,
                )
            )

        return groups

    @staticmethod
    def _build_resolution(
        *,
        packet_id: str,
        total_pages: int,
        groups: list[DocumentGroup],
    ) -> DocumentGroupResolution:
        used_pages = [
            page_number
            for group in groups
            for page_number in group.page_numbers
        ]
        expected = set(range(1, total_pages + 1))
        actual = set(used_pages)

        counts: dict[int, int] = {}

        for page_number in used_pages:
            counts[page_number] = counts.get(page_number, 0) + 1

        duplicates = sorted(
            page_number
            for page_number, count in counts.items()
            if count > 1
        )
        ungrouped = sorted(expected - actual)

        return DocumentGroupResolution(
            packet_id=packet_id,
            groups=groups,
            total_pages=total_pages,
            grouped_pages=len(used_pages),
            ungrouped_pages=ungrouped,
            duplicate_pages=duplicates,
            integrity_valid=not ungrouped and not duplicates,
        )

    @staticmethod
    def _apply_group_ids(
        buckets: list[DocumentBucket],
    ) -> None:
        for bucket in buckets:
            for page in bucket.pages:
                page.document_group_id = bucket.bucket_id

    @staticmethod
    def _bucket_by_id(
        buckets: list[DocumentBucket],
        bucket_id: str,
    ) -> DocumentBucket:
        for bucket in buckets:
            if bucket.bucket_id == bucket_id:
                return bucket

        raise KeyError(f"Bucket not found: {bucket_id}")

    @classmethod
    def _feature(
        cls,
        page: PageInventoryItem,
        key: str,
    ) -> Any:
        snake = cls._camel_to_snake(key)

        for candidate in (key, snake):
            value = getattr(page, candidate, None)

            if value not in (None, ""):
                return value

        aliases = {
            "patientName": "patient_name",
            "claimNumber": "claim_number",
            "mrn": "mrn",
            "ipNumber": "ip_number",
            "payerName": "payer_name",
            "billNumber": "bill_number",
        }
        identifier_field = aliases.get(key, snake)
        identifiers = getattr(page, "identifiers", None)

        if identifiers is not None:
            value = getattr(identifiers, identifier_field, None)

            if value not in (None, ""):
                return value

        financial_aliases = {
            "documentDate": "document_date",
            "totalAmount": "total_amount",
        }
        financial = getattr(page, "financial_metadata", None)

        if financial is not None:
            value = getattr(
                financial,
                financial_aliases.get(key, snake),
                None,
            )

            if value not in (None, ""):
                return value

        evidence = getattr(page, "evidence", None)
        custom = getattr(evidence, "custom_features", None)

        if isinstance(custom, dict):
            containers = [custom]

            for nested_key in (
                "vision",
                "visionEvidence",
                "vision_evidence",
                "documentFingerprint",
                "document_fingerprint",
            ):
                nested = custom.get(nested_key)

                if isinstance(nested, dict):
                    containers.append(nested)

            candidate_keys = {
                key,
                snake,
                key[0].lower() + key[1:] if key else key,
            }

            fingerprint_aliases = {
                "patientName": "patient_name",
                "claimNumber": "claim_number",
                "authorizationNumber": "authorization_number",
                "billNumber": "bill_number",
                "policyNumber": "policy_number",
                "memberId": "member_id",
                "printedPageNumber": "printed_page_number",
                "printedTotalPages": "printed_total_pages",
                "templateSignature": "template_signature",
                "headerSignature": "header_signature",
                "documentDate": "document_date",
            }
            candidate_keys.add(fingerprint_aliases.get(key, snake))

            for container in containers:
                for candidate in candidate_keys:
                    value = container.get(candidate)

                    if value not in (None, ""):
                        return value

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

        return str(value or "").strip().lower() in {
            "1",
            "true",
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
    def _normalise_identifier(value: Any) -> str:
        return "".join(
            character
            for character in str(value or "").upper()
            if character.isalnum()
        )

    @staticmethod
    def _camel_to_snake(value: str) -> str:
        result: list[str] = []

        for character in value:
            if character.isupper():
                result.append("_")
                result.append(character.lower())
            else:
                result.append(character)

        return "".join(result).lstrip("_")


__all__ = [
    "BucketCandidateScore",
    "BucketReviewItem",
    "BucketStatus",
    "DocumentBucket",
    "DocumentBucketResolver",
]
