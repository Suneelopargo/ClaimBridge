# app/services/rule_engine/validation_run_repository.py

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.claim_validation_result import (
    ClaimValidationResult,
)
from app.models.claim_validation_run import (
    ClaimValidationRun,
)
from app.services.rule_engine.models import ExecutedRuleResult


class ValidationRunRepository:

    def __init__(self, db: Session):
        self.db = db

    def create_run(
        self,
        *,
        claim_id: str,
        patient_name: str | None,
        payer_code: str | None,
        source_manifest_path: str | None = None,
    ) -> ClaimValidationRun:
        validation_run = ClaimValidationRun(
            claim_id=claim_id,
            patient_name=patient_name,
            payer_code=payer_code,
            source_manifest_path=source_manifest_path,
            status="RUNNING",
            readiness_score=None,
            total_rules=0,
            applicable_rules=0,
            passed_rules=0,
            failed_rules=0,
            warning_rules=0,
            not_applicable_rules=0,
            manual_review_rules=0,
            started_at=datetime.utcnow(),
        )

        self.db.add(validation_run)
        self.db.flush()

        return validation_run

    def save_result(
        self,
        *,
        validation_run: ClaimValidationRun,
        executed_result: ExecutedRuleResult,
    ) -> ClaimValidationResult:
        rule = executed_result.rule
        applicability = executed_result.applicability
        operator_result = executed_result.operator_result

        if operator_result is None:
            result_status = applicability.status
            result_message = applicability.message
            evidence: dict[str, Any] = (
                applicability.evidence or {}
            )
            review_required = (
                applicability.status == "MANUAL_REVIEW"
            )
        else:
            result_status = operator_result.status
            result_message = operator_result.message
            evidence = operator_result.evidence or {}
            review_required = (
                operator_result.review_required
            )

        result = ClaimValidationResult(
            validation_run_id=validation_run.id,
            rule_id=rule.rule_id,
            rule_version_id=rule.rule_version_id,
            applicability_status=applicability.status,
            result_status=result_status,
            severity=rule.severity,
            result_message=result_message,
            evidence=evidence,
            review_required=review_required,
            evaluated_at=datetime.utcnow(),
        )

        self.db.add(result)
        self.db.flush()

        return result

    def complete_run(
        self,
        *,
        validation_run: ClaimValidationRun,
        status: str,
        readiness_score: float,
        total_rules: int,
        applicable_rules: int,
        passed_rules: int,
        failed_rules: int,
        warning_rules: int,
        manual_review_rules: int,
        not_applicable_rules: int,
    ) -> ClaimValidationRun:
        validation_run.status = status
        validation_run.readiness_score = readiness_score
        validation_run.total_rules = total_rules
        validation_run.applicable_rules = applicable_rules
        validation_run.passed_rules = passed_rules
        validation_run.failed_rules = failed_rules
        validation_run.warning_rules = warning_rules
        validation_run.manual_review_rules = (
            manual_review_rules
        )
        validation_run.not_applicable_rules = (
            not_applicable_rules
        )
        validation_run.completed_at = datetime.utcnow()

        self.db.flush()

        return validation_run

    def mark_failed(
        self,
        *,
        validation_run: ClaimValidationRun,
    ) -> None:
        validation_run.status = "ERROR"
        validation_run.completed_at = datetime.utcnow()
        self.db.flush()