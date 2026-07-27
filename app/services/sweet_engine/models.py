# app/services/sweet_engine/models.py

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.sweet_engine.enums import (
    ClassificationSource,
    PageBoundaryType,
    PageProcessingStatus,
    ReviewPriority,
    ReviewReasonCode,
)


@dataclass
class ClassificationCandidate:
    document_type: str
    confidence: float
    reason: str = ""
    source: ClassificationSource = ClassificationSource.VISION
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.document_type = (
            str(self.document_type or "UNKNOWN")
            .strip()
            .upper()
        )

        try:
            self.confidence = float(self.confidence)
        except (TypeError, ValueError):
            self.confidence = 0.0

        self.confidence = max(0.0, min(1.0, self.confidence))


@dataclass
class PageIdentifiers:
    patient_name: str = ""
    claim_number: str = ""
    mrn: str = ""
    ip_number: str = ""
    payer_name: str = ""
    bill_number: str = ""

    def known_values(self) -> dict[str, str]:
        return {
            key: value
            for key, value in asdict(self).items()
            if str(value or "").strip()
        }


@dataclass
class PageFinancialMetadata:
    document_date: str = ""
    total_amount: str = ""


@dataclass
class PageEvidence:
    extracted_text: str = ""
    headings: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    detected_labels: list[str] = field(default_factory=list)

    has_table: bool = False
    has_signature: bool = False
    has_hospital_logo: bool = False
    has_patient_identifier: bool = False
    has_page_number: bool = False

    page_number_text: str = ""
    header_text: str = ""
    footer_text: str = ""

    image_quality_score: float | None = None
    ocr_confidence: float | None = None
    visual_confidence: float | None = None

    custom_features: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewInformation:
    required: bool = False
    reason_code: ReviewReasonCode | None = None
    priority: ReviewPriority = ReviewPriority.LOW
    message: str = ""
    suggested_action: str = ""
    alternatives: list[ClassificationCandidate] = field(default_factory=list)


@dataclass
class PageInventoryItem:
    page_id: str
    packet_id: str
    page_number: int

    image_path: str | None = None
    source_pdf_path: str | None = None

    status: PageProcessingStatus = PageProcessingStatus.PENDING

    raw_document_type: str = "UNKNOWN"
    final_document_type: str = "UNKNOWN"
    confidence: float = 0.0

    classification_source: ClassificationSource = (
        ClassificationSource.UNRESOLVED
    )

    candidates: list[ClassificationCandidate] = field(
        default_factory=list
    )

    identifiers: PageIdentifiers = field(
        default_factory=PageIdentifiers
    )

    financial_metadata: PageFinancialMetadata = field(
        default_factory=PageFinancialMetadata
    )

    evidence: PageEvidence = field(
        default_factory=PageEvidence
    )

    boundary_type: PageBoundaryType = (
        PageBoundaryType.UNKNOWN
    )

    document_group_id: str | None = None
    previous_page_number: int | None = None
    next_page_number: int | None = None

    review: ReviewInformation = field(
        default_factory=ReviewInformation
    )

    processing_notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.page_number <= 0:
            raise ValueError("page_number must be greater than zero")

        self.raw_document_type = (
            str(self.raw_document_type or "UNKNOWN")
            .strip()
            .upper()
        )

        self.final_document_type = (
            str(self.final_document_type or "UNKNOWN")
            .strip()
            .upper()
        )

        try:
            self.confidence = float(self.confidence)
        except (TypeError, ValueError):
            self.confidence = 0.0

        self.confidence = max(0.0, min(1.0, self.confidence))

    @property
    def is_resolved(self) -> bool:
        return (
            self.final_document_type != "UNKNOWN"
            and self.status
            in {
                PageProcessingStatus.CLASSIFIED,
                PageProcessingStatus.CONTEXT_INFERRED,
            }
        )

    @property
    def requires_review(self) -> bool:
        return (
            self.review.required
            or self.status == PageProcessingStatus.REVIEW_REQUIRED
        )

    def add_candidate(
        self,
        candidate: ClassificationCandidate,
    ) -> None:
        self.candidates.append(candidate)
        self.candidates.sort(
            key=lambda item: item.confidence,
            reverse=True,
        )

    def top_candidate(
        self,
    ) -> ClassificationCandidate | None:
        return self.candidates[0] if self.candidates else None

    def add_processing_note(self, message: str) -> None:
        clean_message = str(message or "").strip()

        if clean_message:
            self.processing_notes.append(clean_message)

    def add_error(self, message: str) -> None:
        clean_message = str(message or "").strip()

        if clean_message:
            self.errors.append(clean_message)
            self.status = PageProcessingStatus.ERROR

    def mark_for_review(
        self,
        reason_code: ReviewReasonCode,
        message: str,
        suggested_action: str,
        priority: ReviewPriority = ReviewPriority.MEDIUM,
        alternatives: list[ClassificationCandidate] | None = None,
    ) -> None:
        self.status = PageProcessingStatus.REVIEW_REQUIRED

        self.review = ReviewInformation(
            required=True,
            reason_code=reason_code,
            priority=priority,
            message=message,
            suggested_action=suggested_action,
            alternatives=alternatives or [],
        )

    def resolve_classification(
        self,
        document_type: str,
        confidence: float,
        source: ClassificationSource,
        note: str | None = None,
    ) -> None:
        normalized_type = (
            str(document_type or "UNKNOWN")
            .strip()
            .upper()
        )

        self.final_document_type = normalized_type
        self.confidence = max(
            0.0,
            min(1.0, float(confidence or 0)),
        )
        self.classification_source = source

        if normalized_type == "UNKNOWN":
            self.status = PageProcessingStatus.REVIEW_REQUIRED
        elif source == ClassificationSource.CONTEXT:
            self.status = PageProcessingStatus.CONTEXT_INFERRED
        else:
            self.status = PageProcessingStatus.CLASSIFIED

        if note:
            self.add_processing_note(note)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)