# app/services/rule_engine/rule_execution_service.py

from __future__ import annotations

from app.services.rule_engine.models import (
    ClaimValidationContext,
    ExecutedRuleResult,
    RuleDefinition,
)
from app.services.rule_engine.rule_executor import RuleExecutor


class RuleExecutionService:

    def __init__(
        self,
        *,
        rule_executor: RuleExecutor,
    ) -> None:
        self.rule_executor = rule_executor

    def execute_rules(
        self,
        *,
        rules: list[RuleDefinition],
        context: ClaimValidationContext,
    ) -> list[ExecutedRuleResult]:
        results: list[ExecutedRuleResult] = []

        for rule in rules:
            result = self.rule_executor.execute_rule(
                rule=rule,
                context=context,
            )
            results.append(result)

        return results