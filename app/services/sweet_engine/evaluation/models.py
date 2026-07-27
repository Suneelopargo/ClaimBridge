# app/services/sweet_engine/evaluation/models.py

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.sweet_engine.enums import PageBoundaryType


@dataclass
class GroundTruthPage:
    page_number: int
    document_type: str
    boundary_type: PageBoundaryType = PageBoundaryType.UNKNOWN
    document_group_id: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if self.page_number <= 0:
            raise ValueError("page_number must be greater than zero")

        self.document_type = (
            str(self.document_type or "UNKNOWN")
            .strip()
            .upper()
        )


@dataclass
class PacketGroundTruth:
    packet_id: str
    source_file: str
    pages: list[GroundTruthPage]
    annotated_by: str = ""
    annotation_date: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.packet_id.strip():
            raise ValueError("packet_id is required")

        page_numbers = [
            page.page_number
            for page in self.pages
        ]

        if len(page_numbers) != len(set(page_numbers)):
            raise ValueError(
                "Ground truth contains duplicate page numbers"
            )

    def get_page(
        self,
        page_number: int,
    ) -> GroundTruthPage | None:
        return next(
            (
                page
                for page in self.pages
                if page.page_number == page_number
            ),
            None,
        )


@dataclass
class PageEvaluationResult:
    page_number: int

    expected_document_type: str
    predicted_document_type: str
    raw_document_type: str

    expected_boundary_type: str
    predicted_boundary_type: str

    initial_confidence: float
    final_confidence: float

    classification_source: str
    processing_status: str

    initially_uncertain: bool
    context_recovered: bool
    review_required: bool

    classification_correct: bool
    boundary_correct: bool | None
    safe_auto_recovery: bool | None

    review_reason_code: str | None = None
    review_message: str = ""

    vision_reason: str = ""
    headings: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    identifier_values: dict[str, str] = field(default_factory=dict)

    processing_notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvaluationMetrics:
    packet_id: str

    total_pages: int
    evaluated_pages: int
    missing_ground_truth_pages: int
    missing_inventory_pages: int

    correctly_classified_pages: int
    incorrectly_classified_pages: int
    classification_accuracy_percent: float

    initially_uncertain_pages: int
    context_recovered_pages: int
    correctly_context_recovered_pages: int
    incorrectly_context_recovered_pages: int

    context_recovery_rate_percent: float
    context_recovery_precision_percent: float
    false_auto_recovery_rate_percent: float

    final_review_pages: int
    human_review_rate_percent: float
    review_reduction_percent: float

    boundary_evaluated_pages: int
    correctly_detected_boundaries: int
    boundary_accuracy_percent: float

    dropped_pages: int
    page_integrity_valid: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PacketEvaluationReport:
    packet_id: str
    source_file: str
    metrics: EvaluationMetrics
    pages: list[PageEvaluationResult]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "packetId": self.packet_id,
            "sourceFile": self.source_file,
            "metrics": self.metrics.to_dict(),
            "warnings": self.warnings,
            "pages": [
                page.to_dict()
                for page in self.pages
            ],
        }