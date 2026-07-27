# app/services/sweet_engine/evaluation/report_builder.py

from __future__ import annotations

import csv
import json
from pathlib import Path

from app.services.sweet_engine.evaluation.models import (
    PacketEvaluationReport,
)


class EvaluationReportBuilder:
    def write_json(
        self,
        report: PacketEvaluationReport,
        output_path: str | Path,
    ) -> Path:
        path = Path(output_path)
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                report.to_dict(),
                file,
                indent=2,
                ensure_ascii=False,
            )

        return path

    def write_csv(
        self,
        report: PacketEvaluationReport,
        output_path: str | Path,
    ) -> Path:
        path = Path(output_path)
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        fieldnames = [
            "pageNumber",
            "expectedDocumentType",
            "predictedDocumentType",
            "rawDocumentType",
            "initialConfidence",
            "finalConfidence",
            "classificationSource",
            "processingStatus",
            "initiallyUncertain",
            "contextRecovered",
            "reviewRequired",
            "classificationCorrect",
            "safeAutoRecovery",
            "expectedBoundaryType",
            "predictedBoundaryType",
            "boundaryCorrect",
            "reviewReasonCode",
            "reviewMessage",
            "processingNotes",
            "errors",
        ]

        with path.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=fieldnames,
            )
            writer.writeheader()

            for page in report.pages:
                writer.writerow(
                    {
                        "pageNumber": page.page_number,
                        "expectedDocumentType": (
                            page.expected_document_type
                        ),
                        "predictedDocumentType": (
                            page.predicted_document_type
                        ),
                        "rawDocumentType": (
                            page.raw_document_type
                        ),
                        "initialConfidence": (
                            page.initial_confidence
                        ),
                        "finalConfidence": (
                            page.final_confidence
                        ),
                        "classificationSource": (
                            page.classification_source
                        ),
                        "processingStatus": (
                            page.processing_status
                        ),
                        "initiallyUncertain": (
                            page.initially_uncertain
                        ),
                        "contextRecovered": (
                            page.context_recovered
                        ),
                        "reviewRequired": (
                            page.review_required
                        ),
                        "classificationCorrect": (
                            page.classification_correct
                        ),
                        "safeAutoRecovery": (
                            page.safe_auto_recovery
                        ),
                        "expectedBoundaryType": (
                            page.expected_boundary_type
                        ),
                        "predictedBoundaryType": (
                            page.predicted_boundary_type
                        ),
                        "boundaryCorrect": (
                            page.boundary_correct
                        ),
                        "reviewReasonCode": (
                            page.review_reason_code
                        ),
                        "reviewMessage": (
                            page.review_message
                        ),
                        "processingNotes": " | ".join(
                            page.processing_notes
                        ),
                        "errors": " | ".join(
                            page.errors
                        ),
                    }
                )

        return path