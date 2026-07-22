from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app.models  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.services.rule_engine.models import (  # noqa: E402
    ClaimValidationContext,
)
from app.services.rule_engine.registry_factory import (  # noqa: E402
    build_default_operator_registry,
)
from app.services.rule_engine.rule_executor import (  # noqa: E402
    RuleExecutor,
)
from app.services.rule_engine.rule_loader import (  # noqa: E402
    RuleLoader,
)


def main() -> None:
    db = SessionLocal()

    try:
        loader = RuleLoader(db)

        rules = loader.load_published_rules(
            payer_code="INSURANCE_TPA",
        )

        print(f"Published rules loaded: {len(rules)}")

        context = ClaimValidationContext(
            claim_id="TEST-HCG-CLAIM-001",
            payer_code="INSURANCE_TPA",
            patient_name="Ramesh Kumar",
            manifest={
                "documents": [
                    {
                        "documentType": "Claim Form Part B",
                        "fileName": "claim_form_part_b.pdf",
                        "pageNumbers": [1, 2],
                        "confidence": 0.96,
                    },
                    {
                        "documentType": "Final Approval Letter",
                        "fileName": "final_approval.pdf",
                        "pageNumbers": [3],
                        "confidence": 0.95,
                    },
                    {
                        "documentType": "Discharge Summary",
                        "fileName": "discharge_summary.pdf",
                        "pageNumbers": [4, 5],
                        "confidence": 0.94,
                    },
                    {
                        "documentType": "Final Hospital Bill",
                        "fileName": "final_bill.pdf",
                        "pageNumbers": [6, 7],
                        "confidence": 0.97,
                    },
                ]
            },
        )

        executor = RuleExecutor(
            operator_registry=(
                build_default_operator_registry()
            )
        )

        passed = 0
        failed = 0
        manual_review = 0
        not_applicable = 0

        for rule in rules:
            result = executor.execute_rule(
                rule=rule,
                context=context,
            )

            print()
            print("=" * 80)
            print(f"Rule: {rule.rule_code}")
            print(f"Name: {rule.rule_name}")
            print(
                "Applicability:",
                result.applicability.status,
            )

            if not result.applicability.applicable:
                if (
                    result.applicability.status
                    == "NOT_APPLICABLE"
                ):
                    not_applicable += 1
                else:
                    manual_review += 1

                print(
                    "Message:",
                    result.applicability.message,
                )
                continue

            operator_result = result.operator_result

            if operator_result is None:
                manual_review += 1
                print(
                    "Status: MANUAL_REVIEW"
                )
                print(
                    "Message: No operator result returned."
                )
                continue

            print(
                "Status:",
                operator_result.status,
            )
            print(
                "Message:",
                operator_result.message,
            )
            print(
                "Evidence:",
                operator_result.evidence,
            )

            if operator_result.status == "PASS":
                passed += 1
            elif operator_result.status == "FAIL":
                failed += 1
            else:
                manual_review += 1

        print()
        print("=" * 80)
        print("Execution Summary")
        print(f"Total rules: {len(rules)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Manual review: {manual_review}")
        print(f"Not applicable: {not_applicable}")

    finally:
        db.close()


if __name__ == "__main__":
    main()