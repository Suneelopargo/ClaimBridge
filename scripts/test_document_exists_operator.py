# scripts/test_document_exists_operator.py

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.rule_engine.models import (  # noqa: E402
    ClaimValidationContext,
    RuleDefinition,
)
from app.services.rule_engine.registry_factory import (  # noqa: E402
    build_default_operator_registry,
)
from app.services.rule_engine.rule_executor import (  # noqa: E402
    RuleExecutor,
)


def main() -> None:
    rule = RuleDefinition(
        rule_id=1,
        rule_code="TEST-DOC-001",
        rule_name="Final Bill Required",
        category="DOCUMENT",
        rule_type="DOCUMENT_EXISTS",
        severity="ERROR",
        rule_version_id=1,
        version_number=1,
        applicability_expression={},
        validation_expression={
            "operator": "DOCUMENT_EXISTS",
            "documentTypes": [
                "Final Bill",
            ],
            "matchMode": "ALL",
        },
        success_message=None,
        failure_message=None,
        required_document_types=[],
    )

    context = ClaimValidationContext(
        claim_id="TEST-CLAIM-001",
        payer_code="INSURANCE_TPA",
        patient_name="Ramesh Kumar",
        manifest={
            "documents": [
                {
                    "documentType": "Final Hospital Bill",
                    "fileName": "final_bill.pdf",
                    "pageNumbers": [8, 9],
                    "confidence": 0.97,
                },
                {
                    "documentType": "Discharge Summary",
                    "fileName": "discharge_summary.pdf",
                    "pageNumbers": [5, 6],
                    "confidence": 0.94,
                },
            ]
        },
    )

    executor = RuleExecutor(
        operator_registry=(
            build_default_operator_registry()
        )
    )

    result = executor.execute_rule(
        rule=rule,
        context=context,
    )

    print(f"Rule: {result.rule.rule_code}")
    print(
        "Applicability:",
        result.applicability.status,
    )

    if result.operator_result:
        print(
            "Status:",
            result.operator_result.status,
        )
        print(
            "Message:",
            result.operator_result.message,
        )
        print(
            "Evidence:",
            result.operator_result.evidence,
        )


if __name__ == "__main__":
    main()