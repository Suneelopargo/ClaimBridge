# app/services/rule_engine/report_models.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidationResultReport:
    result_id: int | None
    rule_id: int
    rule_version_id: int
    rule_code: str
    rule_name: str
    severity: str
    applicability_status: str
    result_status: str
    message: str | None
    evidence: dict[str, Any] = field(default_factory=dict)
    review_required: bool = False


@dataclass(frozen=True)
class ValidationRunReport:
    run_id: int
    claim_id: str
    patient_name: str | None
    payer_code: str | None
    status: str
    readiness_score: float
    total_rules: int
    applicable_rules: int
    passed_rules: int
    failed_rules: int
    warning_rules: int
    manual_review_rules: int
    not_applicable_rules: int
    results: list[ValidationResultReport] = field(
        default_factory=list
    )