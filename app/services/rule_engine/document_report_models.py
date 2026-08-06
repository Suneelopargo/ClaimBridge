from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


VALID_CUSTOMER_STATUSES = {
    "PASS",
    "FAIL",
    "REVIEW",
    "NA",
}


@dataclass(frozen=True)
class DocumentRuleResult:
    rule_number: int
    rule_code: str
    rule_name: str
    status: str

    reason: str | None = None

    evidence: dict[str, Any] = field(
        default_factory=dict
    )

    confidence: float | None = None
    requires_human_review: bool = False

    def __post_init__(self) -> None:
        normalized_status = str(
            self.status or ""
        ).strip().upper()

        if (
            normalized_status
            not in VALID_CUSTOMER_STATUSES
        ):
            raise ValueError(
                "Document rule status must be "
                "PASS, FAIL, REVIEW or NA"
            )

        object.__setattr__(
            self,
            "status",
            normalized_status,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ruleNumber": self.rule_number,
            "ruleCode": self.rule_code,
            "ruleName": self.rule_name,
            "status": self.status,
            "reason": self.reason,
            "confidence": self.confidence,
            "requiresHumanReview": (
                self.requires_human_review
            ),
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class DocumentValidationSummary:
    total_rules: int
    applicable_rules: int
    pass_count: int
    fail_count: int
    review_count: int
    na_count: int
    readiness_percent: float
    review_percent: float
    decision_coverage_percent: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "totalRules": self.total_rules,
            "applicableRules": (
                self.applicable_rules
            ),
            "passCount": self.pass_count,
            "failCount": self.fail_count,
            "reviewCount": self.review_count,
            "naCount": self.na_count,
            "readinessPercent": (
                self.readiness_percent
            ),
            "reviewPercent": (
                self.review_percent
            ),
            "decisionCoveragePercent": (
                self.decision_coverage_percent
            ),
        }


@dataclass(frozen=True)
class DocumentValidationReport:
    document_id: str
    document_type: str
    display_name: str
    page_numbers: list[int]
    file_path: str | None

    summary: DocumentValidationSummary

    rule_results: list[
        DocumentRuleResult
    ] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "documentId": self.document_id,
            "documentType": (
                self.document_type
            ),
            "displayName": self.display_name,
            "pageNumbers": self.page_numbers,
            "filePath": self.file_path,
            "summary": self.summary.to_dict(),
            "ruleResults": [
                result.to_dict()
                for result in self.rule_results
            ],
        }


@dataclass(frozen=True)
class ClaimDocumentValidationReport:
    claim_id: str
    patient_name: str | None
    patient_folder: str | None
    payer_code: str | None

    source_manifest_path: str
    source_manifest_type: str
    generated_at: str

    summary: DocumentValidationSummary

    rules: list[
        dict[str, Any]
    ] = field(default_factory=list)

    documents: list[
        DocumentValidationReport
    ] = field(default_factory=list)

    insights: dict[str, Any] = field(
        default_factory=dict
    )

    rule_set_name: str = (
        "HCG Document Validation MVP"
    )

    rule_set_version: str = "MVP-1.0"

    configured_rule_count: int = 28

    catalogue_rule_count: int = 72

    def to_dict(self) -> dict[str, Any]:
        return {
            "claimId": self.claim_id,
            "patientName": self.patient_name,
            "patientFolder": (
                self.patient_folder
            ),
            "payerCode": self.payer_code,
            "sourceManifestPath": (
                self.source_manifest_path
            ),
            "sourceManifestType": (
                self.source_manifest_type
            ),
            "generatedAt": self.generated_at,
            "summary": self.summary.to_dict(),
            "insights": self.insights,
            "rules": self.rules,
            "documents": [
                document.to_dict()
                for document in self.documents
            ],
            "ruleSet": {
                "name": self.rule_set_name,
                "version": (
                    self.rule_set_version
                ),
                "configuredRuleCount": (
                    self.configured_rule_count
                ),
                "catalogueRuleCount": (
                    self.catalogue_rule_count
                ),
                "scope": (
                    "Manifest-based validation "
                    "of segregated documents"
                ),
            },
        }


@dataclass(frozen=True)
class ClaimPacketInventoryItem:
    claim_id: str
    patient_name: str | None
    patient_folder: str | None
    claim_directory: str

    source_manifest_path: str
    source_manifest_type: str

    document_count: int
    review_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "claimId": self.claim_id,
            "patientName": self.patient_name,
            "patientFolder": (
                self.patient_folder
            ),
            "claimDirectory": (
                self.claim_directory
            ),
            "sourceManifestPath": (
                self.source_manifest_path
            ),
            "sourceManifestType": (
                self.source_manifest_type
            ),
            "documentCount": (
                self.document_count
            ),
            "reviewStatus": (
                self.review_status
            ),
        }