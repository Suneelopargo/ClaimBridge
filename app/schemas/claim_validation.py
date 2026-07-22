from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


class ApiSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        from_attributes=True,
    )


class ClaimValidationRequest(ApiSchema):
    claim_id: str
    payer_code: str | None = None
    patient_name: str | None = None
    source_manifest_path: str | None = None
    manifest: dict[str, Any]


class ValidationResultResponse(ApiSchema):
    rule_id: int
    rule_version_id: int
    rule_code: str
    rule_name: str
    severity: str
    applicability_status: str
    result_status: str
    message: str | None = None
    review_required: bool = False
    evidence: dict[str, Any]


class ValidationRunResponse(ApiSchema):
    run_id: int
    claim_id: str
    patient_name: str | None = None
    payer_code: str | None = None
    status: str
    readiness_score: float
    total_rules: int
    applicable_rules: int
    passed_rules: int
    failed_rules: int
    warning_rules: int
    manual_review_rules: int
    not_applicable_rules: int
    results: list[ValidationResultResponse]