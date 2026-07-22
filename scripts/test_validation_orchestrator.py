# scripts/test_validation_orchestrator.py

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app.models  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.services.rule_engine.orchestrator_factory import (  # noqa: E402
    build_validation_orchestrator,
)


def main() -> None:
    db = SessionLocal()

    try:
        orchestrator = (
            build_validation_orchestrator(db)
        )

        report = orchestrator.run_validation(
            claim_id="TEST-HCG-CLAIM-001",
            payer_code="INSURANCE_TPA",
            patient_name="Ramesh Kumar",
            manifest={
                "documents": [
                    {
                        "documentType": (
                            "Claim Form Part B"
                        ),
                        "fileName": (
                            "claim_form_part_b.pdf"
                        ),
                        "pageNumbers": [1, 2],
                        "confidence": 0.96,
                    },
                    {
                        "documentType": (
                            "Final Approval Letter"
                        ),
                        "fileName": (
                            "final_approval.pdf"
                        ),
                        "pageNumbers": [3],
                        "confidence": 0.95,
                    },
                    {
                        "documentType": (
                            "Discharge Summary"
                        ),
                        "fileName": (
                            "discharge_summary.pdf"
                        ),
                        "pageNumbers": [4, 5],
                        "confidence": 0.94,
                    },
                    {
                        "documentType": (
                            "Final Hospital Bill"
                        ),
                        "fileName": "final_bill.pdf",
                        "pageNumbers": [6, 7],
                        "confidence": 0.97,
                    },
                ]
            },
        )

        print()
        print("=" * 80)
        print("Validation Run")
        print(f"Run ID: {report.run_id}")
        print(f"Claim ID: {report.claim_id}")
        print(f"Status: {report.status}")
        print(
            "Readiness score:",
            report.readiness_score,
        )
        print(f"Total rules: {report.total_rules}")
        print(
            "Applicable rules:",
            report.applicable_rules,
        )
        print(f"Passed: {report.passed_rules}")
        print(f"Failed: {report.failed_rules}")
        print(f"Warnings: {report.warning_rules}")
        print(
            "Manual review:",
            report.manual_review_rules,
        )
        print(
            "Not applicable:",
            report.not_applicable_rules,
        )

        for result in report.results:
            print()
            print(
                result.rule_code,
                result.result_status,
                "-",
                result.message,
            )

    finally:
        db.close()


if __name__ == "__main__":
    main()