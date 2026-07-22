# app/services/rule_engine/operators/base.py

from __future__ import annotations

from abc import ABC, abstractmethod

from app.services.rule_engine.manifest_accessor import (
    ManifestAccessor,
)
from app.services.rule_engine.models import (
    ClaimValidationContext,
    OperatorResult,
    RuleDefinition,
)


class BaseRuleOperator(ABC):

    @abstractmethod
    def execute(
        self,
        *,
        rule: RuleDefinition,
        context: ClaimValidationContext,
        manifest: ManifestAccessor,
    ) -> OperatorResult:
        raise NotImplementedError