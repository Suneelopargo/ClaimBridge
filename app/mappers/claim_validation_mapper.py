from app.schemas.claim_validation import ValidationRunResponse, ValidationResultResponse
from app.services.rule_engine.report_models import ValidationRunReport


class ClaimValidationMapper:

    @staticmethod
    def to_response(
            report: ValidationRunReport,
    ) -> ValidationRunResponse:
        return ValidationRunResponse(
            run_id=report.run_id,
            claim_id=report.claim_id,
            patient_name=report.patient_name,
            payer_code=report.payer_code,
            status=report.status,
            readiness_score=report.readiness_score,
            total_rules=report.total_rules,
            applicable_rules=report.applicable_rules,
            passed_rules=report.passed_rules,
            failed_rules=report.failed_rules,
            warning_rules=report.warning_rules,
            manual_review_rules=report.manual_review_rules,
            not_applicable_rules=report.not_applicable_rules,
            results=[
                ValidationResultResponse(
                    rule_id=r.rule_id,
                    rule_version_id=r.rule_version_id,
                    rule_code=r.rule_code,
                    rule_name=r.rule_name,
                    severity=r.severity,
                    applicability_status=r.applicability_status,
                    result_status=r.result_status,
                    message=r.message,
                    evidence=r.evidence,
                    review_required=r.review_required,
                )
                for r in report.results
            ],
        )