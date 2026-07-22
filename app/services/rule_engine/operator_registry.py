# app/services/rule_engine/operator_registry.py

from __future__ import annotations

from typing import Protocol

from app.services.rule_engine.manifest_accessor import (
    ManifestAccessor,
)
from app.services.rule_engine.models import (
    ClaimValidationContext,
    OperatorResult,
    RuleDefinition,
)


class RuleOperator(Protocol):

    def execute(
        self,
        *,
        rule: RuleDefinition,
        context: ClaimValidationContext,
        manifest: ManifestAccessor,
    ) -> OperatorResult:
        ...


class OperatorRegistry:

    def __init__(self) -> None:
        self._operators: dict[str, RuleOperator] = {}

    def register(
        self,
        operator_name: str,
        operator: RuleOperator,
    ) -> None:
        normalized_name = self._normalize(
            operator_name
        )

        if not normalized_name:
            raise ValueError(
                "Operator name cannot be blank"
            )

        if normalized_name in self._operators:
            raise ValueError(
                f"Operator '{normalized_name}' is "
                "already registered"
            )

        self._operators[normalized_name] = operator

    def get(
        self,
        operator_name: str,
    ) -> RuleOperator | None:
        return self._operators.get(
            self._normalize(operator_name)
        )

    def registered_operator_names(
        self,
    ) -> list[str]:
        return sorted(self._operators.keys())

    @staticmethod
    def _normalize(
        value: str | None,
    ) -> str:
        return str(value or "").strip().upper()