# app/services/sweet_engine/page_inventory.py

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Any
from uuid import uuid4

from app.services.sweet_engine.enums import (
    ClassificationSource,
    PageProcessingStatus,
    ReviewPriority,
    ReviewReasonCode,
)
from app.services.sweet_engine.models import (
    ClassificationCandidate,
    PageFinancialMetadata,
    PageIdentifiers,
    PageInventoryItem,
)


class PageInventory:
    def __init__(
        self,
        packet_id: str,
        total_pages: int,
        source_pdf_path: str | None = None,
    ) -> None:
        if not packet_id or not packet_id.strip():
            raise ValueError("packet_id is required")

        if total_pages <= 0:
            raise ValueError("total_pages must be greater than zero")

        self.packet_id = packet_id.strip()
        self.total_pages = total_pages
        self.source_pdf_path = source_pdf_path
        self.pages: list[PageInventoryItem] = []

    def initialize_pages(self) -> None:
        if self.pages:
            raise ValueError(
                "Page inventory has already been initialized"
            )

        for page_number in range(1, self.total_pages + 1):
            self.pages.append(
                PageInventoryItem(
                    page_id=str(uuid4()),
                    packet_id=self.packet_id,
                    page_number=page_number,
                    source_pdf_path=self.source_pdf_path,
                    previous_page_number=(
                        page_number - 1
                        if page_number > 1
                        else None
                    ),
                    next_page_number=(
                        page_number + 1
                        if page_number < self.total_pages
                        else None
                    ),
                )
            )

    def get_page(
        self,
        page_number: int,
    ) -> PageInventoryItem:
        for page in self.pages:
            if page.page_number == page_number:
                return page

        raise KeyError(
            f"Page {page_number} not found in packet "
            f"{self.packet_id}"
        )

    def previous_page(
        self,
        page_number: int,
    ) -> PageInventoryItem | None:
        if page_number <= 1:
            return None

        return self.get_page(page_number - 1)

    def next_page(
        self,
        page_number: int,
    ) -> PageInventoryItem | None:
        if page_number >= self.total_pages:
            return None

        return self.get_page(page_number + 1)

    def apply_vision_result(
        self,
        page_number: int,
        classification: dict[str, Any],
        image_path: str | None = None,
        extracted_text: str = "",
        minimum_confidence: float = 0.70,

    ) -> PageInventoryItem:
        page = self.get_page(page_number)
        initial_confidence: float = 0.0

        raw_document_type = str(
            classification.get("documentType") or "UNKNOWN"
        ).strip().upper()

        try:
            confidence = float(
                classification.get("confidence") or 0
            )
        except (TypeError, ValueError):
            confidence = 0.0

        confidence = max(0.0, min(1.0, confidence))

        candidate = ClassificationCandidate(
            document_type=raw_document_type,
            confidence=confidence,
            reason=str(
                classification.get("reason") or ""
            ),
            source=ClassificationSource.VISION,
        )

        page.image_path = image_path
        page.raw_document_type = raw_document_type
        page.evidence.extracted_text = extracted_text or ""
        page.add_candidate(candidate)
        page.initial_confidence = confidence
        page.confidence = confidence

        page.identifiers = PageIdentifiers(
            patient_name=str(
                classification.get("patientName") or ""
            ),
            claim_number=str(
                classification.get("claimNumber") or ""
            ),
            mrn=str(classification.get("mrn") or ""),
            ip_number=str(
                classification.get("ipNumber") or ""
            ),
            payer_name=str(
                classification.get("payerName") or ""
            ),
            bill_number=str(
                classification.get("billNumber") or ""
            ),
        )

        page.financial_metadata = PageFinancialMetadata(
            document_date=str(
                classification.get("documentDate") or ""
            ),
            total_amount=str(
                classification.get("totalAmount") or ""
            ),
        )

        if raw_document_type != "UNKNOWN" and confidence >= minimum_confidence:
            page.resolve_classification(
                document_type=raw_document_type,
                confidence=confidence,
                source=ClassificationSource.VISION,
                note=(
                    "Page classified directly from Vision "
                    f"with confidence {confidence:.2f}."
                ),
            )
        else:
            page.final_document_type = "UNKNOWN"

            reason_message = self._build_initial_review_message(
                raw_document_type=raw_document_type,
                confidence=confidence,
                model_reason=candidate.reason,
            )

            page.mark_for_review(
                reason_code=(
                    ReviewReasonCode.LOW_CLASSIFICATION_CONFIDENCE
                    if raw_document_type != "UNKNOWN"
                    else ReviewReasonCode.AMBIGUOUS_DOCUMENT_TYPE
                ),
                message=reason_message,
                suggested_action=(
                    "Review this page after neighbouring-page "
                    "context and document grouping are evaluated."
                ),
                priority=ReviewPriority.MEDIUM,
                alternatives=[candidate],
            )

        return page

    def validate_no_page_drop(self) -> list[str]:
        errors: list[str] = []

        if len(self.pages) != self.total_pages:
            errors.append(
                "Inventory page count mismatch: "
                f"expected {self.total_pages}, "
                f"found {len(self.pages)}."
            )

        actual_page_numbers = {
            page.page_number
            for page in self.pages
        }

        expected_page_numbers = set(
            range(1, self.total_pages + 1)
        )

        missing_pages = sorted(
            expected_page_numbers - actual_page_numbers
        )

        duplicate_counts = Counter(
            page.page_number
            for page in self.pages
        )

        duplicate_pages = sorted(
            page_number
            for page_number, count in duplicate_counts.items()
            if count > 1
        )

        if missing_pages:
            errors.append(
                f"Missing inventory pages: {missing_pages}"
            )

        if duplicate_pages:
            errors.append(
                f"Duplicate inventory pages: {duplicate_pages}"
            )

        return errors

    def assert_no_page_drop(self) -> None:
        errors = self.validate_no_page_drop()

        if errors:
            raise ValueError("; ".join(errors))

    def unresolved_pages(self) -> list[PageInventoryItem]:
        return [
            page
            for page in self.pages
            if not page.is_resolved
        ]

    def review_required_pages(
        self,
    ) -> list[PageInventoryItem]:
        return [
            page
            for page in self.pages
            if page.requires_review
        ]

    def classified_pages(
        self,
    ) -> list[PageInventoryItem]:
        return [
            page
            for page in self.pages
            if page.is_resolved
        ]

    def pages_by_document_type(
        self,
        document_type: str,
    ) -> list[PageInventoryItem]:
        normalized_type = document_type.strip().upper()

        return [
            page
            for page in self.pages
            if page.final_document_type == normalized_type
        ]

    def summary(self) -> dict[str, Any]:
        status_counts = Counter(
            page.status.value
            for page in self.pages
        )

        document_type_counts = Counter(
            page.final_document_type
            for page in self.pages
        )

        context_recovered_pages = len([
            page
            for page in self.pages
            if page.status
               == PageProcessingStatus.CONTEXT_INFERRED
        ])

        directly_classified_pages = len([
            page
            for page in self.pages
            if (
                    page.status == PageProcessingStatus.CLASSIFIED
                    and page.classification_source
                    == ClassificationSource.VISION
            )
        ])

        initially_uncertain_pages = len([
            page
            for page in self.pages
            if (
                    page.raw_document_type == "UNKNOWN"
                    or (
                            page.candidates
                            and page.candidates[0].confidence < 0.70
                    )
            )
        ])

        final_review_pages = len(
            self.review_required_pages()
        )

        review_reduction_percent = (
            round(
                (
                        context_recovered_pages
                        / initially_uncertain_pages
                )
                * 100,
                2,
            )
            if initially_uncertain_pages > 0
            else 0.0
        )

        no_page_drop_errors = self.validate_no_page_drop()

        return {
            "packetId": self.packet_id,
            "totalPages": self.total_pages,
            "inventoryPages": len(self.pages),

            "directlyClassifiedPages": directly_classified_pages,
            "initiallyUncertainPages": initially_uncertain_pages,
            "contextRecoveredPages": context_recovered_pages,
            "finalReviewPages": final_review_pages,
            "reviewReductionPercent": review_reduction_percent,

            "classifiedPages": len(self.classified_pages()),
            "reviewRequiredPages": final_review_pages,
            "unresolvedPages": len(self.unresolved_pages()),

            "statusCounts": dict(status_counts),
            "documentTypeCounts": dict(document_type_counts),

            "droppedPages": (
                0 if not no_page_drop_errors
                else self.total_pages - len(self.pages)
            ),
            "pageIntegrityValid": not no_page_drop_errors,
            "pageIntegrityErrors": no_page_drop_errors,
        }

    def to_manifest_dict(self) -> dict[str, Any]:
        self.assert_no_page_drop()

        return {
            "packetId": self.packet_id,
            "totalPages": self.total_pages,
            "summary": self.summary(),
            "pages": [
                asdict(page)
                for page in self.pages
            ],
        }

    @staticmethod
    def _build_initial_review_message(
        raw_document_type: str,
        confidence: float,
        model_reason: str,
    ) -> str:
        if raw_document_type == "UNKNOWN":
            base_message = (
                "The page could not be assigned to a reliable "
                "document type during initial classification."
            )
        else:
            base_message = (
                f"The page appears to be {raw_document_type}, "
                f"but confidence is only {confidence:.2f}, "
                "which is below the automatic classification threshold."
            )

        if model_reason:
            return f"{base_message} Model evidence: {model_reason}"

        return base_message