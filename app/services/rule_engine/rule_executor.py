from __future__ import annotations

from app.services.rule_engine.applicability import (
    ApplicabilityEvaluator,
)
from app.services.rule_engine.models import (
    ApplicabilityResult,
    ClaimValidationContext,
    ExecutedRuleResult,
    OperatorResult,
    RuleDefinition,
)
from app.services.rule_engine.operator_registry import (
    OperatorRegistry,
)

from app.services.rule_engine.manifest_accessor import (
    ManifestAccessor,
)


class RuleExecutor:
    def __init__(
        self,
        *,
        operator_registry: OperatorRegistry,
        applicability_evaluator: (
            ApplicabilityEvaluator | None
        ) = None,
    ) -> None:
        self.operator_registry = operator_registry
        self.applicability_evaluator = (
            applicability_evaluator
            or ApplicabilityEvaluator()
        )

    def execute_rule(
        self,
        *,
        rule: RuleDefinition,
        context: ClaimValidationContext,
    ) -> ExecutedRuleResult:
        applicability = (
            self.applicability_evaluator.evaluate(
                rule=rule,
                context=context,
            )
        )

        if not applicability.applicable:
            return ExecutedRuleResult(
                rule=rule,
                applicability=applicability,
                operator_result=None,
            )

        operator_name = self._resolve_operator_name(
            rule
        )

        operator = self.operator_registry.get(
            operator_name
        )

        if operator is None:
            return ExecutedRuleResult(
                rule=rule,
                applicability=applicability,
                operator_result=OperatorResult(
                    status="NOT_EVALUATED",
                    message=(
                        f"No implementation is registered "
                        f"for operator '{operator_name}'."
                    ),
                    evidence={
                        "operator": operator_name,
                        "validationExpression": (
                            rule.validation_expression
                        ),
                    },
                    review_required=True,
                ),
            )

        manifest = ManifestAccessor(
            context.manifest
        )

        try:
            result = operator.execute(
                rule=rule,
                context=context,
                manifest=manifest,
            )

        except Exception as exc:
            result = OperatorResult(
                status="MANUAL_REVIEW",
                message=(
                    "Rule execution failed and requires "
                    "manual review."
                ),
                evidence={
                    "operator": operator_name,
                    "errorType": type(exc).__name__,
                    "error": str(exc),
                    "manifestSummary": manifest.summary(),
                },
                review_required=True,
            )
        return ExecutedRuleResult(
            rule=rule,
            applicability=applicability,
            operator_result=result,
        )

    @staticmethod
    def _resolve_operator_name(
        rule: RuleDefinition,
    ) -> str:
        expression_operator = (
            rule.validation_expression.get("operator")
        )

        return str(
            expression_operator or rule.rule_type
        ).strip().upper()