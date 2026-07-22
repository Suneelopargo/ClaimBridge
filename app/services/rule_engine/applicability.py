from __future__ import annotations

from typing import Any

from app.services.rule_engine.models import (
    ApplicabilityResult,
    ClaimValidationContext,
    RuleDefinition,
)


class ApplicabilityEvaluator:
    def evaluate(
        self,
        *,
        rule: RuleDefinition,
        context: ClaimValidationContext,
    ) -> ApplicabilityResult:
        expression = rule.applicability_expression or {}

        if not expression:
            return ApplicabilityResult(
                applicable=True,
                status="APPLICABLE",
                message="No applicability restriction configured.",
            )

        operator = str(
            expression.get("operator", "")
        ).strip().upper()

        if not operator:
            return ApplicabilityResult(
                applicable=True,
                status="APPLICABLE",
                message="No applicability operator configured.",
                evidence={"expression": expression},
            )

        if operator == "PAYER_IN":
            return self._evaluate_payer_in(
                expression=expression,
                context=context,
            )

        return ApplicabilityResult(
            applicable=False,
            status="MANUAL_REVIEW",
            message=(
                f"Unsupported applicability operator: "
                f"{operator}"
            ),
            evidence={"expression": expression},
        )

    @staticmethod
    def _evaluate_payer_in(
        *,
        expression: dict[str, Any],
        context: ClaimValidationContext,
    ) -> ApplicabilityResult:
        configured_payers = {
            str(value).strip().upper()
            for value in expression.get("payerTypes", [])
            if str(value).strip()
        }

        if not configured_payers:
            return ApplicabilityResult(
                applicable=True,
                status="APPLICABLE",
                message="Rule applies to all payer types.",
                evidence={
                    "configuredPayers": [],
                    "claimPayer": context.payer_code,
                },
            )

        if not context.payer_code:
            return ApplicabilityResult(
                applicable=False,
                status="MANUAL_REVIEW",
                message=(
                    "Claim payer is unavailable; payer "
                    "applicability could not be determined."
                ),
                evidence={
                    "configuredPayers": sorted(
                        configured_payers
                    ),
                    "claimPayer": None,
                },
            )

        claim_payer = context.payer_code.strip().upper()
        applicable = claim_payer in configured_payers

        return ApplicabilityResult(
            applicable=applicable,
            status=(
                "APPLICABLE"
                if applicable
                else "NOT_APPLICABLE"
            ),
            message=(
                "Claim payer is included in the rule."
                if applicable
                else "Rule does not apply to the claim payer."
            ),
            evidence={
                "configuredPayers": sorted(
                    configured_payers
                ),
                "claimPayer": claim_payer,
            },
        )