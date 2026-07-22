from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RuleDefinition:
    rule_id: int
    rule_code: str
    rule_name: str
    category: str
    rule_type: str
    severity: str

    rule_version_id: int
    version_number: int

    applicability_expression: dict[str, Any]
    validation_expression: dict[str, Any]

    success_message: str | None = None
    failure_message: str | None = None

    required_document_types: list[str] = field(
        default_factory=list
    )


@dataclass(frozen=True)
class ClaimValidationContext:
    claim_id: str
    payer_code: str | None
    patient_name: str | None
    manifest: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ApplicabilityResult:
    applicable: bool
    status: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OperatorResult:
    status: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)
    review_required: bool = False


@dataclass(frozen=True)
class ExecutedRuleResult:
    rule: RuleDefinition
    applicability: ApplicabilityResult
    operator_result: OperatorResult | None