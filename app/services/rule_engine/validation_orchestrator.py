# app/services/rule_engine/validation_orchestrator.py

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.rule_engine.models import (
    ClaimValidationContext,
    ExecutedRuleResult,
)
from app.services.rule_engine.report_models import (
    ValidationResultReport,
    ValidationRunReport,
)
from app.services.rule_engine.rule_execution_service import (
    RuleExecutionService,
)
from app.services.rule_engine.rule_loader import RuleLoader
from app.services.rule_engine.validation_run_repository import (
    ValidationRunRepository,
)


@dataclass
class ValidationCounters:
    total_rules: int = 0
    applicable_rules: int = 0
    passed_rules: int = 0
    failed_rules: int = 0
    warning_rules: int = 0
    manual_review_rules: int = 0
    not_applicable_rules: int = 0


class ValidationOrchestrator:

    def __init__(
        self,
        *,
        db: Session,
        rule_loader: RuleLoader,
        execution_service: RuleExecutionService,
        repository: ValidationRunRepository,
    ) -> None:
        self.db = db
        self.rule_loader = rule_loader
        self.execution_service = execution_service
        self.repository = repository

    def run_validation(
        self,
        *,
        claim_id: str,
        payer_code: str | None,
        patient_name: str | None,
        manifest: dict,
        source_manifest_path: str | None = None,
    ) -> ValidationRunReport:
        validation_run = self.repository.create_run(
            claim_id=claim_id,
            patient_name=patient_name,
            payer_code=payer_code,
            source_manifest_path=source_manifest_path,
        )

        try:
            rules = self.rule_loader.load_published_rules(
                payer_code=payer_code,
            )

            context = ClaimValidationContext(
                claim_id=claim_id,
                payer_code=payer_code,
                patient_name=patient_name,
                manifest=manifest,
            )

            executed_results = (
                self.execution_service.execute_rules(
                    rules=rules,
                    context=context,
                )
            )

            counters = ValidationCounters(
                total_rules=len(rules)
            )

            reports: list[ValidationResultReport] = []

            for executed_result in executed_results:
                persisted_result = (
                    self.repository.save_result(
                        validation_run=validation_run,
                        executed_result=executed_result,
                    )
                )

                self._update_counters(
                    counters=counters,
                    result=executed_result,
                )

                reports.append(
                    self._to_result_report(
                        persisted_result_id=(
                            persisted_result.id
                        ),
                        result=executed_result,
                    )
                )

            readiness_score = (
                self._calculate_readiness_score(
                    counters
                )
            )

            overall_status = (
                self._determine_overall_status(
                    counters
                )
            )

            self.repository.complete_run(
                validation_run=validation_run,
                status=overall_status,
                readiness_score=readiness_score,
                total_rules=counters.total_rules,
                applicable_rules=(
                    counters.applicable_rules
                ),
                passed_rules=counters.passed_rules,
                failed_rules=counters.failed_rules,
                warning_rules=counters.warning_rules,
                manual_review_rules=(
                    counters.manual_review_rules
                ),
                not_applicable_rules=(
                    counters.not_applicable_rules
                ),
            )

            self.db.commit()

            return ValidationRunReport(
                run_id=validation_run.id,
                claim_id=validation_run.claim_id,
                patient_name=(
                    validation_run.patient_name
                ),
                payer_code=validation_run.payer_code,
                status=validation_run.status,
                readiness_score=readiness_score,
                total_rules=counters.total_rules,
                applicable_rules=(
                    counters.applicable_rules
                ),
                passed_rules=counters.passed_rules,
                failed_rules=counters.failed_rules,
                warning_rules=counters.warning_rules,
                manual_review_rules=(
                    counters.manual_review_rules
                ),
                not_applicable_rules=(
                    counters.not_applicable_rules
                ),
                results=reports,
            )

        except Exception:

            self.db.rollback()

            raise

    @staticmethod
    def _update_counters(
        *,
        counters: ValidationCounters,
        result: ExecutedRuleResult,
    ) -> None:
        applicability = result.applicability

        if applicability.status == "NOT_APPLICABLE":
            counters.not_applicable_rules += 1
            return

        if applicability.status == "MANUAL_REVIEW":
            counters.manual_review_rules += 1
            return

        counters.applicable_rules += 1

        operator_result = result.operator_result

        if operator_result is None:
            counters.manual_review_rules += 1
            return

        status = operator_result.status.upper()

        if status == "PASS":
            counters.passed_rules += 1
        elif status == "FAIL":
            counters.failed_rules += 1
        elif status == "WARNING":
            counters.warning_rules += 1
        else:
            counters.manual_review_rules += 1

    @staticmethod
    def _calculate_readiness_score(
        counters: ValidationCounters,
    ) -> float:
        denominator = counters.applicable_rules

        if denominator == 0:
            return 0.0

        earned_score = (
            counters.passed_rules
            + (counters.warning_rules * 0.5)
        )

        score = (
            earned_score / denominator
        ) * 100

        return round(score, 2)

    @staticmethod
    def _determine_overall_status(
        counters: ValidationCounters,
    ) -> str:
        if counters.failed_rules > 0:
            return "FAILED"

        if counters.manual_review_rules > 0:
            return "MANUAL_REVIEW"

        if counters.warning_rules > 0:
            return "WARNING"

        if (
            counters.applicable_rules == 0
            and counters.total_rules > 0
        ):
            return "NOT_APPLICABLE"

        if counters.total_rules == 0:
            return "NO_RULES"

        return "PASSED"

    @staticmethod
    def _to_result_report(
        *,
        persisted_result_id: int,
        result: ExecutedRuleResult,
    ) -> ValidationResultReport:
        operator_result = result.operator_result

        if operator_result is None:
            result_status = (
                result.applicability.status
            )
            message = result.applicability.message
            evidence = (
                result.applicability.evidence or {}
            )
            review_required = (
                result.applicability.status
                == "MANUAL_REVIEW"
            )
        else:
            result_status = operator_result.status
            message = operator_result.message
            evidence = operator_result.evidence or {}
            review_required = (
                operator_result.review_required
            )

        return ValidationResultReport(
            result_id=persisted_result_id,
            rule_id=result.rule.rule_id,
            rule_version_id=(
                result.rule.rule_version_id
            ),
            rule_code=result.rule.rule_code,
            rule_name=result.rule.rule_name,
            severity=result.rule.severity,
            applicability_status=(
                result.applicability.status
            ),
            result_status=result_status,
            message=message,
            evidence=evidence,
            review_required=review_required,
        )