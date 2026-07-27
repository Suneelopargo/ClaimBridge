# app/services/sweet_engine/evaluation/evaluator.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.sweet_engine.enums import (
    ClassificationSource,
    PageBoundaryType,
)
from app.services.sweet_engine.evaluation.metrics import (
    calculate_evaluation_metrics,
)
from app.services.sweet_engine.evaluation.models import (
    GroundTruthPage,
    PacketEvaluationReport,
    PacketGroundTruth,
    PageEvaluationResult,
)
from app.services.sweet_engine.page_inventory import PageInventory


def load_ground_truth(
    file_path: str | Path,
) -> PacketGroundTruth:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Ground-truth file not found: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        payload: dict[str, Any] = json.load(file)

    pages = [
        GroundTruthPage(
            page_number=int(item["pageNumber"]),
            document_type=str(
                item.get("documentType") or "UNKNOWN"
            ),
            boundary_type=_parse_boundary_type(
                item.get("boundaryType")
                or item.get("boundary")
                or "UNKNOWN"
            ),
            document_group_id=item.get("documentGroupId"),
            notes=str(item.get("notes") or ""),
        )
        for item in payload.get("pages", [])
    ]

    return PacketGroundTruth(
        packet_id=str(payload.get("packetId") or "").strip(),
        source_file=str(payload.get("sourceFile") or ""),
        pages=pages,
        annotated_by=str(payload.get("annotatedBy") or ""),
        annotation_date=str(
            payload.get("annotationDate") or ""
        ),
        notes=str(payload.get("notes") or ""),
    )


class PacketEvaluator:
    def evaluate(
        self,
        inventory: PageInventory,
        ground_truth: PacketGroundTruth,
    ) -> PacketEvaluationReport:
        if inventory.packet_id != ground_truth.packet_id:
            raise ValueError(
                "Packet ID mismatch: "
                f"inventory={inventory.packet_id}, "
                f"ground_truth={ground_truth.packet_id}"
            )

        inventory_pages = {
            page.page_number: page
            for page in inventory.pages
        }

        truth_pages = {
            page.page_number: page
            for page in ground_truth.pages
        }

        all_page_numbers = sorted(
            set(inventory_pages)
            | set(truth_pages)
        )

        results: list[PageEvaluationResult] = []
        warnings: list[str] = []

        for page_number in all_page_numbers:
            inventory_page = inventory_pages.get(page_number)
            truth_page = truth_pages.get(page_number)

            if inventory_page is None:
                warnings.append(
                    f"Page {page_number} exists in ground truth "
                    "but is missing from inventory."
                )
                continue

            if truth_page is None:
                warnings.append(
                    f"Page {page_number} exists in inventory "
                    "but has no ground-truth annotation."
                )
                continue

            expected_type = truth_page.document_type
            predicted_type = (
                inventory_page.final_document_type
            )

            classification_correct = (
                expected_type == predicted_type
            )

            expected_boundary = (
                truth_page.boundary_type.value
            )
            predicted_boundary = (
                inventory_page.boundary_type.value
            )

            boundary_correct: bool | None

            if (
                truth_page.boundary_type
                == PageBoundaryType.UNKNOWN
            ):
                boundary_correct = None
            else:
                boundary_correct = (
                    expected_boundary
                    == predicted_boundary
                )

            context_recovered = (
                inventory_page.classification_source
                == ClassificationSource.CONTEXT
            )

            safe_auto_recovery: bool | None = None

            if context_recovered:
                safe_auto_recovery = classification_correct

            initial_confidence = _initial_confidence(
                inventory_page
            )

            initially_uncertain = (
                inventory_page.raw_document_type == "UNKNOWN"
                or initial_confidence < 0.70
            )

            review_reason_code = (
                inventory_page.review.reason_code.value
                if inventory_page.review.reason_code
                else None
            )

            results.append(
                PageEvaluationResult(
                    page_number=page_number,
                    expected_document_type=expected_type,
                    predicted_document_type=predicted_type,
                    raw_document_type=(
                        inventory_page.raw_document_type
                    ),
                    expected_boundary_type=(
                        expected_boundary
                    ),
                    predicted_boundary_type=(
                        predicted_boundary
                    ),
                    initial_confidence=initial_confidence,
                    final_confidence=(
                        inventory_page.confidence
                    ),
                    classification_source=(
                        inventory_page
                        .classification_source
                        .value
                    ),
                    processing_status=(
                        inventory_page.status.value
                    ),
                    initially_uncertain=(
                        initially_uncertain
                    ),
                    context_recovered=context_recovered,
                    review_required=(
                        inventory_page.requires_review
                    ),
                    classification_correct=(
                        classification_correct
                    ),
                    boundary_correct=boundary_correct,
                    safe_auto_recovery=(
                        safe_auto_recovery
                    ),
                    review_reason_code=(
                        review_reason_code
                    ),
                    review_message=(
                        inventory_page.review.message
                    ),
                    processing_notes=list(
                        inventory_page.processing_notes
                    ),
                    errors=list(
                        inventory_page.errors
                    ),
                )
            )

        metrics = calculate_evaluation_metrics(
            packet_id=inventory.packet_id,
            inventory=inventory,
            ground_truth=ground_truth,
            results=results,
        )

        return PacketEvaluationReport(
            packet_id=inventory.packet_id,
            source_file=ground_truth.source_file,
            metrics=metrics,
            pages=results,
            warnings=warnings,
        )


def _parse_boundary_type(
    value: str,
) -> PageBoundaryType:
    normalized = (
        str(value or "UNKNOWN")
        .strip()
        .upper()
    )

    try:
        return PageBoundaryType(normalized)
    except ValueError:
        return PageBoundaryType.UNKNOWN


def _initial_confidence(
    page: Any,
) -> float:
    top_candidate = page.top_candidate()

    if top_candidate is not None:
        return float(top_candidate.confidence)

    return float(page.confidence or 0)