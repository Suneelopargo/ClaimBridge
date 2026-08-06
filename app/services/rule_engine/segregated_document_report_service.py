from __future__ import annotations

import json
import re

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.rule_engine.document_report_models import (
    ClaimDocumentValidationReport,
    DocumentRuleResult,
    DocumentValidationReport,
    DocumentValidationSummary,
)
from app.services.rule_engine.segregated_packet_inventory_service import (
    SegregatedPacketInventoryService,
)


HONORIFICS = {
    "MR",
    "MRS",
    "MS",
    "MISS",
    "SMT",
    "SHRI",
    "SRI",
    "DR",
    "MASTER",
    "BABY",
}


DOCUMENT_SPECIFIC_RULES = {
    51: {
        "name": "Preauthorization Form",
        "documentTypes": {
            "PREAUTHORIZATION_FORM",
        },
    },
    52: {
        "name": "Claim Form Part B",
        "documentTypes": {
            "CLAIM_FORM",
        },
    },
    53: {
        "name": "GIPSA PPN Declaration",
        "documentTypes": {
            "GIPSA_DECLARATION",
            "PPN_DECLARATION",
            "FORM_CONTINUATION",
        },
    },
    54: {
        "name": "KYC Form and Details",
        "documentTypes": {
            "KYC_DOCUMENT",
        },
    },
    55: {
        "name": "Patient Photo ID Proof",
        "documentTypes": {
            "PATIENT_ID_PROOF",
            "INSURANCE_CARD",
        },
    },
    56: {
        "name": "Supporting Prescription and Reports",
        "documentTypes": {
            "PRESCRIPTION",
            "INVESTIGATION_REPORT",
            "LAB_REPORT",
            "RADIOLOGY_REPORT",
        },
    },
    57: {
        "name": "Consent or Declaration Forms",
        "documentTypes": {
            "CONSENT_FORM",
        },
    },
    58: {
        "name": "Approval or Referral Letter",
        "documentTypes": {
            "APPROVAL_LETTER",
            "CASHLESS_AUTHORIZATION_LETTER",
            "AUTHORIZATION_CONTINUATION",
        },
    },
    59: {
        "name": "Discharge, Death or Transfer Summary",
        "documentTypes": {
            "DISCHARGE_SUMMARY",
            "DEATH_SUMMARY",
            "TRANSFER_SUMMARY",
        },
    },
    60: {
        "name": "Indoor Case Papers",
        "documentTypes": {
            "CASE_PAPER",
            "OT_NOTES",
            "TREATMENT_ORDER",
        },
    },
    61: {
        "name": "All Investigation Reports",
        "documentTypes": {
            "INVESTIGATION_REPORT",
            "LAB_REPORT",
            "RADIOLOGY_REPORT",
        },
    },
    62: {
        "name": "Laboratory, Radiology or NMD Reports",
        "documentTypes": {
            "LAB_REPORT",
            "RADIOLOGY_REPORT",
            "INVESTIGATION_REPORT",
        },
    },
    63: {
        "name": "CT, MRI, X-Ray or USG Films",
        "documentTypes": {
            "RADIOLOGY_FILM",
            "CT_FILM",
            "MRI_FILM",
            "XRAY_FILM",
            "USG_FILM",
        },
    },
    64: {
        "name": "Implant Sticker and Invoice",
        "documentTypes": {
            "IMPLANT_STICKER_INVOICE",
        },
    },
    65: {
        "name": "Blood Component Stickers",
        "documentTypes": {
            "BLOOD_COMPONENT_STICKER",
            "BLOOD_BANK_REPORT",
        },
    },
    66: {
        "name": "Patient Procedure Photographs",
        "documentTypes": {
            "PATIENT_PHOTO",
        },
    },
    67: {
        "name": "Police FIR or MLC",
        "documentTypes": {
            "FIR",
            "MLC",
            "MEDICO_LEGAL_CERTIFICATE",
        },
    },
    68: {
        "name": "Final Bill",
        "documentTypes": {
            "FINAL_HOSPITAL_BILL",
            "BILL_CONTINUATION",
            "DETAILED_BILL_BREAKUP",
        },
    },
    69: {
        "name": "Payment and Refund Receipt",
        "documentTypes": {
            "PAYMENT_RECEIPT",
            "REFUND_RECEIPT",
        },
    },
    70: {
        "name": "Package or Profile Break-up",
        "documentTypes": {
            "PACKAGE_BREAKUP",
            "DETAILED_BILL_BREAKUP",
        },
    },
    71: {
        "name": "Pharmacy Details",
        "documentTypes": {
            "PHARMACY_DETAILS",
            "PHARMACY_BILL",
        },
    },
    72: {
        "name": "Feedback Forms",
        "documentTypes": {
            "FEEDBACK_FORM",
        },
    },
}


RULE_NAMES = {
    7: "Patient Identity Validation",
    29: "Date Consistency",
    34: "Report Completeness",
    36: "Document Quality Validation",
    37: "Document Naming Validation",
    38: "File Format Validation",
    **{
        number: definition["name"]
        for number, definition
        in DOCUMENT_SPECIFIC_RULES.items()
    },
}


class SegregatedDocumentReportService:

    def __init__(
        self,
        inventory_service: (
            SegregatedPacketInventoryService
            | None
        ) = None,
    ) -> None:
        self.inventory_service = (
            inventory_service
            or SegregatedPacketInventoryService()
        )

    def generate_report(
        self,
        claim_id: str,
    ) -> ClaimDocumentValidationReport:
        inventory_item, manifest = (
            self.inventory_service.get_claim_packet(
                claim_id
            )
        )

        documents = (
            self.inventory_service
            .extract_documents(manifest)
        )

        canonical_patient_name = (
            self._derive_canonical_patient_name(
                packet_patient_name=(
                    inventory_item.patient_name
                ),
                documents=documents,
            )
        )

        reports = [
            self._validate_document(
                claim_id=inventory_item.claim_id,
                canonical_patient_name=(
                    canonical_patient_name
                ),
                document=document,
            )
            for document in documents
        ]

        claim_summary = (
            self._aggregate_document_summaries(
                reports
            )
        )

        insights = self._build_insights(
            reports=reports,
            summary=claim_summary,
        )

        rules = [
            {
                "ruleNumber": rule_number,
                "ruleCode": (
                    f"HCG-VAL-{rule_number:03d}"
                ),
                "ruleName": rule_name,
            }
            for rule_number, rule_name
            in sorted(RULE_NAMES.items())
        ]

        generated_at = (
            datetime.now().isoformat()
        )

        report = ClaimDocumentValidationReport(
            claim_id=inventory_item.claim_id,
            patient_name=(
                inventory_item.patient_name
            ),
            patient_folder=(
                inventory_item.patient_folder
            ),
            payer_code=self._derive_payer(
                documents
            ),
            source_manifest_path=(
                inventory_item
                .source_manifest_path
            ),
            source_manifest_type=(
                "SEGREGATED_MANIFEST"
            ),
            generated_at=generated_at,
            summary=claim_summary,
            rules=rules,
            documents=reports,
            insights=insights,
        )

        self._persist_report(
            claim_directory=Path(
                inventory_item.claim_directory
            ),
            report=report,
        )

        return report

    def _validate_document(
        self,
        *,
        claim_id: str,
        canonical_patient_name: str,
        document: dict[str, Any],
    ) -> DocumentValidationReport:
        page_number = self._to_int(
            document.get("pageNumber")
        )

        document_type = str(
            document.get("documentType")
            or "UNKNOWN"
        ).strip().upper()

        display_name = (
            document_type
            .replace("_", " ")
            .title()
        )

        document_id = (
            f"{claim_id}-page-"
            f"{page_number:03d}"
        )

        rule_results = [
            self._validate_patient_identity(
                canonical_patient_name=(
                    canonical_patient_name
                ),
                document=document,
            ),
            self._validate_document_date(
                document=document
            ),
            self._validate_completeness(
                document=document
            ),
            self._validate_quality(
                document=document
            ),
            self._validate_naming(
                document=document
            ),
            self._validate_file_format(
                document=document
            ),
        ]

        for rule_number in range(51, 73):
            rule_results.append(
                self._validate_document_specific_rule(
                    rule_number=rule_number,
                    document=document,
                )
            )

        summary = self._summarize_results(
            rule_results
        )

        file_path = str(
            document.get("segregatedFile")
            or ""
        ).strip() or None

        return DocumentValidationReport(
            document_id=document_id,
            document_type=document_type,
            display_name=(
                f"{display_name} – Page "
                f"{page_number}"
            ),
            page_numbers=[page_number],
            file_path=file_path,
            summary=summary,
            rule_results=rule_results,
        )

    def _validate_patient_identity(
            self,
            *,
            canonical_patient_name: str,
            document: dict[str, Any],
    ) -> DocumentRuleResult:
        document_type = str(
            document.get("documentType")
            or ""
        ).strip().upper()

        identity_not_required_types = {
            "AUTHORIZATION_CONTINUATION",
            "BILL_CONTINUATION",
            "FORM_CONTINUATION",
            "PAYMENT_RECEIPT",
            "REFUND_RECEIPT",
            "UNKNOWN",
        }

        if (
                document_type
                in identity_not_required_types
        ):
            return self._result(
                rule_number=7,
                status="NA",
                reason=(
                    "Patient-name validation is "
                    "not mandatory for this "
                    "document page type."
                ),
            )

        actual_name = (
            self._document_patient_name(
                document
            )
        )

        expected_name = (
            canonical_patient_name
        )

        identifier_status = str(
            document.get(
                "identifierVerificationStatus"
            )
            or ""
        ).strip().upper()

        quality_status = str(
            document.get("qualityStatus")
            or ""
        ).strip().upper()

        extraction_source = str(
            document.get("source")
            or ""
        ).strip().upper()

        direct_patient_name = str(
            document.get("patientName")
            or ""
        ).strip()

        name_from_unverified_vision = (
                not direct_patient_name
                and bool(actual_name)
                and identifier_status
                == "UNVERIFIED_SCANNED_PAGE"
        )

        if not actual_name:
            return self._result(
                rule_number=7,
                status="REVIEW",
                reason=(
                    "Patient name could not be "
                    "reliably extracted. Human "
                    "verification is required."
                ),
                confidence=None,
                requires_human_review=True,
                evidence={
                    "expectedPatientName": (
                            expected_name or None
                    ),
                    "actualPatientName": None,
                    "pageNumber": document.get(
                        "pageNumber"
                    ),
                    "qualityStatus": quality_status,
                    "identifierVerificationStatus": (
                        identifier_status
                    ),
                    "extractionSource": (
                        extraction_source
                    ),
                },
            )

        normalized_expected = (
            self._normalize_person_name(
                expected_name
            )
        )

        normalized_actual = (
            self._normalize_person_name(
                actual_name
            )
        )

        exact_match = (
                normalized_expected
                and normalized_actual
                and normalized_expected
                == normalized_actual
        )

        if exact_match:
            return self._result(
                rule_number=7,
                status="PASS",
                reason=(
                    "Normalized patient name "
                    "matches the packet identity."
                ),
                confidence=1.0,
                evidence={
                    "expectedPatientName": (
                        expected_name
                    ),
                    "actualPatientName": actual_name,
                    "normalizedExpected": (
                        normalized_expected
                    ),
                    "normalizedActual": (
                        normalized_actual
                    ),
                    "pageNumber": document.get(
                        "pageNumber"
                    ),
                    "identifierVerificationStatus": (
                        identifier_status
                    ),
                },
            )

        # A mismatch based only on unverified Vision
        # extraction from a scanned/handwritten page
        # is not sufficient to declare the document
        # incorrect.
        if name_from_unverified_vision:
            return self._result(
                rule_number=7,
                status="REVIEW",
                reason=(
                    "The patient name extracted "
                    "from this scanned or handwritten "
                    "document differs from the packet "
                    "identity, but the extraction is "
                    "unverified. Human verification "
                    "is required before declaring a "
                    "business-rule failure."
                ),
                confidence=self._identity_confidence(
                    document=document,
                    expected_name=expected_name,
                    actual_name=actual_name,
                ),
                requires_human_review=True,
                evidence={
                    "expectedPatientName": (
                        expected_name
                    ),
                    "actualPatientName": actual_name,
                    "normalizedExpected": (
                        normalized_expected
                    ),
                    "normalizedActual": (
                        normalized_actual
                    ),
                    "pageNumber": document.get(
                        "pageNumber"
                    ),
                    "qualityStatus": quality_status,
                    "identifierVerificationStatus": (
                        identifier_status
                    ),
                    "extractionSource": (
                        extraction_source
                    ),
                    "evidenceReliability": (
                        "UNVERIFIED_VISION"
                    ),
                },
            )

        # Only verified, sufficiently reliable
        # extracted values may generate a true FAIL.
        return self._result(
            rule_number=7,
            status="FAIL",
            reason=(
                "Verified patient name differs "
                "from the packet identity."
            ),
            confidence=self._identity_confidence(
                document=document,
                expected_name=expected_name,
                actual_name=actual_name,
            ),
            evidence={
                "expectedPatientName": expected_name,
                "actualPatientName": actual_name,
                "normalizedExpected": (
                    normalized_expected
                ),
                "normalizedActual": (
                    normalized_actual
                ),
                "pageNumber": document.get(
                    "pageNumber"
                ),
                "identifierVerificationStatus": (
                    identifier_status
                ),
                "evidenceReliability": (
                    "VERIFIED"
                ),
            },
        )

    def _validate_document_date(
        self,
        *,
        document: dict[str, Any],
    ) -> DocumentRuleResult:
        document_type = str(
            document.get("documentType")
            or ""
        ).upper()

        date_optional_types = {
            "PATIENT_ID_PROOF",
            "INSURANCE_CARD",
            "KYC_DOCUMENT",
            "AUTHORIZATION_CONTINUATION",
            "FORM_CONTINUATION",
            "BILL_CONTINUATION",
        }

        if document_type in date_optional_types:
            return self._result(
                rule_number=29,
                status="NA",
                reason=(
                    "A document date is not "
                    "mandatory for this page type."
                ),
            )

        document_date = str(
            document.get("documentDate")
            or ""
        ).strip()

        identifier_status = str(
            document.get(
                "identifierVerificationStatus"
            )
            or ""
        ).strip().upper()

        quality_status = str(
            document.get("qualityStatus")
            or ""
        ).strip().upper()

        if document_date:
            return self._result(
                rule_number=29,
                status="PASS",
                reason="Document date is available.",
                evidence={
                    "documentDate": document_date,
                    "pageNumber": document.get(
                        "pageNumber"
                    ),
                },
            )

        if (
                identifier_status
                == "UNVERIFIED_SCANNED_PAGE"
                or quality_status
                == "SCANNED_IMAGE"
        ):
            return self._result(
                rule_number=29,
                status="REVIEW",
                reason=(
                    "A document date was not reliably "
                    "extracted from this scanned page. "
                    "Human verification is required."
                ),
                requires_human_review=True,
                evidence={
                    "documentDate": None,
                    "pageNumber": document.get(
                        "pageNumber"
                    ),
                    "qualityStatus": quality_status,
                    "identifierVerificationStatus": (
                        identifier_status
                    ),
                },
            )

        return self._result(
            rule_number=29,
            status="FAIL",
            reason=(
                "The required document date is "
                "confirmed as absent."
            ),
            evidence={
                "documentDate": None,
                "pageNumber": document.get(
                    "pageNumber"
                ),
            },
        )

    def _validate_completeness(
        self,
        *,
        document: dict[str, Any],
    ) -> DocumentRuleResult:
        page_role = str(
            document.get("pageRole")
            or ""
        ).upper()

        printed_page = self._to_optional_int(
            document.get(
                "printedPageNumber"
            )
        )
        printed_total = self._to_optional_int(
            document.get(
                "printedTotalPages"
            )
        )

        if page_role == "UNKNOWN":
            return self._result(
                rule_number=34,
                status="FAIL",
                reason=(
                    "Page role could not be "
                    "determined."
                ),
            )

        if (
            printed_page is not None
            and printed_total is not None
            and printed_page > printed_total
        ):
            return self._result(
                rule_number=34,
                status="FAIL",
                reason=(
                    "Printed page number exceeds "
                    "the printed total page count."
                ),
                evidence={
                    "printedPageNumber": (
                        printed_page
                    ),
                    "printedTotalPages": (
                        printed_total
                    ),
                },
            )

        return self._result(
            rule_number=34,
            status="PASS",
            reason=(
                "Page role and page-sequence "
                "metadata are internally valid."
            ),
            evidence={
                "pageRole": page_role,
                "printedPageNumber": printed_page,
                "printedTotalPages": printed_total,
                "explicitDocumentStart": (
                    document.get(
                        "explicitDocumentStart"
                    )
                ),
                "explicitDocumentEnd": (
                    document.get(
                        "explicitDocumentEnd"
                    )
                ),
            },
        )

    def _validate_quality(
        self,
        *,
        document: dict[str, Any],
    ) -> DocumentRuleResult:
        confidence = self._to_float(
            document.get("confidence")
        )
        review_required = bool(
            document.get("reviewRequired")
        )
        quality_status = str(
            document.get("qualityStatus")
            or ""
        ).upper()

        passed = (
            confidence >= 0.70
            and not review_required
            and quality_status
            not in {
                "BLURRY",
                "UNREADABLE",
                "BLANK",
                "CUT_OFF",
            }
        )

        return self._result(
            rule_number=36,
            status=(
                "PASS"
                if passed
                else "REVIEW"
            ),
            reason=(
                "Document quality and "
                "classification confidence are "
                "acceptable."
                if passed
                else
                "Document quality or classification "
                "confidence requires human review."
            ),
            confidence=confidence,
            requires_human_review=not passed,
            evidence={
                "confidence": confidence,
                "qualityStatus": quality_status,
                "reviewRequired": review_required,
            },
        )

    def _validate_naming(
            self,
            *,
            document: dict[str, Any],
    ) -> DocumentRuleResult:
        document_type = str(
            document.get("documentType")
            or "UNKNOWN"
        ).strip().upper()

        output_file = str(
            document.get("outputFile")
            or ""
        ).strip().lower()

        confidence = self._to_float(
            document.get("confidence")
        )

        if not output_file:
            return self._result(
                rule_number=37,
                status="REVIEW",
                reason=(
                    "Generated document filename "
                    "is unavailable."
                ),
                confidence=confidence,
                requires_human_review=True,
            )

        filename_token = (
            Path(output_file)
            .stem
            .lower()
            .replace("_", " ")
        )

        if "review required" in filename_token:
            return self._result(
                rule_number=37,
                status="REVIEW",
                reason=(
                    "The segregated file was retained "
                    "with a review-required filename, "
                    "although a document type was "
                    "identified."
                ),
                confidence=confidence,
                requires_human_review=True,
                evidence={
                    "documentType": document_type,
                    "outputFile": output_file,
                    "classificationConfidence": (
                        confidence
                    ),
                },
            )

        expected_tokens = [
            token
            for token in (
                document_type
                .lower()
                .split("_")
            )
            if len(token) > 2
        ]

        passed = (
                document_type != "UNKNOWN"
                and all(
            token in filename_token
            for token in expected_tokens
        )
        )

        return self._result(
            rule_number=37,
            status=(
                "PASS"
                if passed
                else "REVIEW"
            ),
            reason=(
                "Generated filename is consistent "
                "with the classified document type."
                if passed
                else
                "Generated filename and classified "
                "document type require verification."
            ),
            confidence=confidence,
            requires_human_review=not passed,
            evidence={
                "documentType": document_type,
                "outputFile": output_file,
            },
        )

    def _validate_file_format(
        self,
        *,
        document: dict[str, Any],
    ) -> DocumentRuleResult:
        file_path_text = str(
            document.get("segregatedFile")
            or ""
        ).strip()

        if not file_path_text:
            return self._result(
                rule_number=38,
                status="FAIL",
                reason=(
                    "Segregated document path "
                    "is unavailable."
                ),
            )

        file_path = Path(file_path_text)

        passed = (
            file_path.suffix.lower() == ".pdf"
            and file_path.exists()
            and file_path.is_file()
        )

        return self._result(
            rule_number=38,
            status="PASS" if passed else "FAIL",
            reason=(
                "Segregated PDF exists and has "
                "a supported file format."
                if passed
                else
                "Segregated PDF is missing or "
                "has an unsupported format."
            ),
            evidence={
                "filePath": file_path_text,
                "extension": (
                    file_path.suffix.lower()
                ),
                "exists": file_path.exists(),
            },
        )

    def _validate_document_specific_rule(
            self,
            *,
            rule_number: int,
            document: dict[str, Any],
    ) -> DocumentRuleResult:
        definition = (
            DOCUMENT_SPECIFIC_RULES[
                rule_number
            ]
        )

        document_type = str(
            document.get("documentType")
            or ""
        ).strip().upper()

        if (
                document_type
                not in definition["documentTypes"]
        ):
            return self._result(
                rule_number=rule_number,
                status="NA",
                reason=(
                    "Rule does not apply to "
                    f"{document_type or 'UNKNOWN'}."
                ),
            )

        visible_title = str(
            document.get("visibleTitle")
            or ""
        ).strip()

        classification_reason = str(
            document.get("reason")
            or ""
        ).strip()

        confidence = self._to_float(
            document.get("confidence")
        )

        page_role = str(
            document.get("pageRole")
            or ""
        ).strip().upper()

        continuation_indicators = (
                document.get(
                    "continuationIndicators"
                )
                or []
        )

        is_continuation_page = (
                page_role
                in {
                    "CONTINUATION",
                    "END",
                }
                or document_type.endswith(
            "_CONTINUATION"
        )
        )

        if is_continuation_page:
            has_continuation_evidence = bool(
                classification_reason
                and confidence >= 0.70
                and (
                        continuation_indicators
                        or page_role
                        in {
                            "CONTINUATION",
                            "END",
                        }
                )
            )

            return self._result(
                rule_number=rule_number,
                status=(
                    "PASS"
                    if has_continuation_evidence
                    else "REVIEW"
                ),
                reason=(
                    "Continuation page is supported "
                    "by page-role and sequence evidence."
                    if has_continuation_evidence
                    else
                    "Continuation relationship could "
                    "not be established reliably."
                ),
                confidence=confidence,
                requires_human_review=(
                    not has_continuation_evidence
                ),
                evidence={
                    "documentType": document_type,
                    "pageRole": page_role,
                    "visibleTitle": (
                            visible_title or None
                    ),
                    "continuationIndicators": (
                        continuation_indicators
                    ),
                    "classificationReason": (
                            classification_reason
                            or None
                    ),
                    "confidence": confidence,
                },
            )

        if (
                not classification_reason
                or confidence < 0.70
        ):
            return self._result(
                rule_number=rule_number,
                status="REVIEW",
                reason=(
                    "Document-specific evidence "
                    "could not be established "
                    "reliably."
                ),
                confidence=confidence,
                requires_human_review=True,
                evidence={
                    "documentType": document_type,
                    "visibleTitle": (
                            visible_title or None
                    ),
                    "classificationReason": (
                            classification_reason
                            or None
                    ),
                    "confidence": confidence,
                },
            )

        passed = bool(visible_title)

        return self._result(
            rule_number=rule_number,
            status=(
                "PASS"
                if passed
                else "REVIEW"
            ),
            reason=(
                "Document classification, title "
                "and supporting evidence are "
                "available."
                if passed
                else
                "Expected title was not identified; "
                "human verification is required."
            ),
            confidence=confidence,
            requires_human_review=not passed,
            evidence={
                "documentType": document_type,
                "visibleTitle": (
                        visible_title or None
                ),
                "classificationReason": (
                    classification_reason
                ),
                "confidence": confidence,
            },
        )


    def _result(
            self,
            *,
            rule_number: int,
            status: str,
            reason: str,
            evidence: dict[str, Any]
                      | None = None,
            confidence: float | None = None,
            requires_human_review: bool = False,
    ) -> DocumentRuleResult:
        normalized_status = str(
            status or ""
        ).strip().upper()

        return DocumentRuleResult(
            rule_number=rule_number,
            rule_code=(
                f"HCG-VAL-{rule_number:03d}"
            ),
            rule_name=RULE_NAMES[
                rule_number
            ],
            status=normalized_status,
            reason=reason,
            evidence=evidence or {},
            confidence=confidence,
            requires_human_review=(
                    requires_human_review
                    or normalized_status == "REVIEW"
            ),
        )

    @staticmethod
    def _derive_canonical_patient_name(
        *,
        packet_patient_name: str | None,
        documents: list[dict[str, Any]],
    ) -> str:
        if packet_patient_name:
            return packet_patient_name

        names: list[str] = []

        for document in documents:
            candidate_map = document.get(
                "visionIdentityCandidates"
            )

            if not isinstance(
                candidate_map,
                dict,
            ):
                continue

            value = str(
                candidate_map.get(
                    "patientName"
                )
                or ""
            ).strip()

            if value:
                names.append(value)

        if not names:
            return ""

        normalized_counts = Counter(
            SegregatedDocumentReportService
            ._normalize_person_name(value)
            for value in names
        )

        most_common_normalized, _ = (
            normalized_counts.most_common(1)[0]
        )

        for value in names:
            if (
                SegregatedDocumentReportService
                ._normalize_person_name(value)
                == most_common_normalized
            ):
                return value

        return names[0]

    @staticmethod
    def _document_patient_name(
        document: dict[str, Any],
    ) -> str:
        direct_value = str(
            document.get("patientName")
            or ""
        ).strip()

        if direct_value:
            return direct_value

        candidate_map = document.get(
            "visionIdentityCandidates"
        )

        if not isinstance(candidate_map, dict):
            return ""

        return str(
            candidate_map.get(
                "patientName"
            )
            or ""
        ).strip()

    @staticmethod
    def _normalize_person_name(
        value: str,
    ) -> str:
        tokens = re.findall(
            r"[A-Z0-9]+",
            str(value or "").upper(),
        )

        filtered = [
            token
            for token in tokens
            if token not in HONORIFICS
        ]

        return " ".join(filtered)

    @staticmethod
    def _derive_payer(
        documents: list[dict[str, Any]],
    ) -> str | None:
        payer_values = [
            str(
                document.get("payerName")
                or ""
            ).strip()
            for document in documents
            if str(
                document.get("payerName")
                or ""
            ).strip()
        ]

        if not payer_values:
            return None

        return Counter(
            value.upper()
            for value in payer_values
        ).most_common(1)[0][0]

    @staticmethod
    def _summarize_results(
            results: list[DocumentRuleResult],
    ) -> DocumentValidationSummary:
        pass_count = sum(
            result.status == "PASS"
            for result in results
        )

        fail_count = sum(
            result.status == "FAIL"
            for result in results
        )

        review_count = sum(
            result.status == "REVIEW"
            for result in results
        )

        na_count = sum(
            result.status == "NA"
            for result in results
        )

        applicable = (
                pass_count
                + fail_count
                + review_count
        )

        decided = (
                pass_count
                + fail_count
        )

        readiness = (
            round(
                pass_count
                / decided
                * 100,
                2,
            )
            if decided
            else 0.0
        )

        review_percent = (
            round(
                review_count
                / applicable
                * 100,
                2,
            )
            if applicable
            else 0.0
        )

        decision_coverage = (
            round(
                decided
                / applicable
                * 100,
                2,
            )
            if applicable
            else 0.0
        )

        return DocumentValidationSummary(
            total_rules=len(results),
            applicable_rules=applicable,
            pass_count=pass_count,
            fail_count=fail_count,
            review_count=review_count,
            na_count=na_count,
            readiness_percent=readiness,
            review_percent=review_percent,
            decision_coverage_percent=(
                decision_coverage
            ),
        )

    @classmethod
    def _aggregate_document_summaries(
            cls,
            reports: list[
                DocumentValidationReport
            ],
    ) -> DocumentValidationSummary:
        total_rules = sum(
            report.summary.total_rules
            for report in reports
        )

        pass_count = sum(
            report.summary.pass_count
            for report in reports
        )

        fail_count = sum(
            report.summary.fail_count
            for report in reports
        )

        review_count = sum(
            report.summary.review_count
            for report in reports
        )

        na_count = sum(
            report.summary.na_count
            for report in reports
        )

        applicable = (
                pass_count
                + fail_count
                + review_count
        )

        decided = (
                pass_count
                + fail_count
        )

        readiness = (
            round(
                pass_count
                / decided
                * 100,
                2,
            )
            if decided
            else 0.0
        )

        review_percent = (
            round(
                review_count
                / applicable
                * 100,
                2,
            )
            if applicable
            else 0.0
        )

        decision_coverage = (
            round(
                decided
                / applicable
                * 100,
                2,
            )
            if applicable
            else 0.0
        )

        return DocumentValidationSummary(
            total_rules=total_rules,
            applicable_rules=applicable,
            pass_count=pass_count,
            fail_count=fail_count,
            review_count=review_count,
            na_count=na_count,
            readiness_percent=readiness,
            review_percent=review_percent,
            decision_coverage_percent=(
                decision_coverage
            ),
        )

    @staticmethod
    def _persist_report(
        *,
        claim_directory: Path,
        report: ClaimDocumentValidationReport,
    ) -> None:
        report_directory = (
            claim_directory
            / "validation"
        )

        report_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        report_path = (
            report_directory
            / "document_validation_report.json"
        )

        with report_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                report.to_dict(),
                file,
                indent=2,
                ensure_ascii=False,
            )

    @staticmethod
    def _to_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _to_optional_int(
        value: Any,
    ) -> int | None:
        if value in {None, ""}:
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _identity_confidence(
            cls,
            *,
            document: dict[str, Any],
            expected_name: str,
            actual_name: str,
    ) -> float:
        document_confidence = cls._to_float(
            document.get("confidence")
        )

        identifier_status = str(
            document.get(
                "identifierVerificationStatus"
            )
            or ""
        ).strip().upper()

        normalized_expected = (
            cls._normalize_person_name(
                expected_name
            )
        )

        normalized_actual = (
            cls._normalize_person_name(
                actual_name
            )
        )

        similarity = cls._name_similarity(
            normalized_expected,
            normalized_actual,
        )

        verification_factor = (
            1.0
            if identifier_status
               not in {
                   "",
                   "UNVERIFIED_SCANNED_PAGE",
               }
            else 0.45
        )

        confidence = (
                document_confidence
                * similarity
                * verification_factor
        )

        return round(
            max(0.0, min(confidence, 1.0)),
            3,
        )

    @staticmethod
    def _name_similarity(
            expected: str,
            actual: str,
    ) -> float:
        if not expected or not actual:
            return 0.0

        from difflib import SequenceMatcher

        return SequenceMatcher(
            None,
            expected,
            actual,
        ).ratio()

    @staticmethod
    def _build_insights(
            *,
            reports: list[
                DocumentValidationReport
            ],
            summary: DocumentValidationSummary,
    ) -> dict[str, Any]:
        failed_items: list[
            dict[str, Any]
        ] = []

        review_items: list[
            dict[str, Any]
        ] = []

        fail_rule_counts: Counter[int] = Counter()
        review_rule_counts: Counter[int] = Counter()

        document_type_stats: dict[
            str,
            dict[str, int],
        ] = {}

        for report in reports:
            stats = document_type_stats.setdefault(
                report.document_type,
                {
                    "documentCount": 0,
                    "passCount": 0,
                    "failCount": 0,
                    "reviewCount": 0,
                },
            )

            stats["documentCount"] += 1
            stats["passCount"] += (
                report.summary.pass_count
            )
            stats["failCount"] += (
                report.summary.fail_count
            )
            stats["reviewCount"] += (
                report.summary.review_count
            )

            for result in report.rule_results:
                item = {
                    "documentId": (
                        report.document_id
                    ),
                    "documentType": (
                        report.document_type
                    ),
                    "displayName": (
                        report.display_name
                    ),
                    "pageNumbers": (
                        report.page_numbers
                    ),
                    "filePath": (
                        report.file_path
                    ),
                    "ruleNumber": (
                        result.rule_number
                    ),
                    "ruleCode": (
                        result.rule_code
                    ),
                    "ruleName": (
                        result.rule_name
                    ),
                    "reason": result.reason,
                    "confidence": (
                        result.confidence
                    ),
                    "evidence": result.evidence,
                }

                if result.status == "FAIL":
                    failed_items.append(item)

                    fail_rule_counts[
                        result.rule_number
                    ] += 1

                elif result.status == "REVIEW":
                    review_items.append(item)

                    review_rule_counts[
                        result.rule_number
                    ] += 1

        document_type_summary = []

        for document_type, stats in (
                document_type_stats.items()
        ):
            decided = (
                    stats["passCount"]
                    + stats["failCount"]
            )

            applicable = (
                    decided
                    + stats["reviewCount"]
            )

            readiness = (
                round(
                    stats["passCount"]
                    / decided
                    * 100,
                    2,
                )
                if decided
                else 0.0
            )

            review_rate = (
                round(
                    stats["reviewCount"]
                    / applicable
                    * 100,
                    2,
                )
                if applicable
                else 0.0
            )

            document_type_summary.append(
                {
                    "documentType": (
                        document_type
                    ),
                    **stats,
                    "readinessPercent": (
                        readiness
                    ),
                    "reviewRatePercent": (
                        review_rate
                    ),
                }
            )

        document_type_summary.sort(
            key=lambda item: (
                -item["reviewCount"],
                item["readinessPercent"],
            )
        )

        if summary.fail_count > 0:
            overall_status = "FAILURES_FOUND"
        elif summary.review_count > 0:
            overall_status = "REVIEW_REQUIRED"
        else:
            overall_status = "VALIDATION_COMPLETE"

        return {
            "overallStatus": overall_status,
            "headline": (
                "No confirmed discrepancies were "
                "found, but human verification is "
                "required for some validations."
                if overall_status
                   == "REVIEW_REQUIRED"
                else
                "Confirmed validation failures "
                "were identified."
                if overall_status
                   == "FAILURES_FOUND"
                else
                "All applicable validations were "
                "completed without discrepancies."
            ),
            "confirmedReadinessPercent": (
                summary.readiness_percent
            ),
            "decisionCoveragePercent": (
                summary.decision_coverage_percent
            ),
            "humanReviewBurdenPercent": (
                summary.review_percent
            ),
            "genuineFailureCount": len(
                failed_items
            ),
            "humanReviewCount": len(
                review_items
            ),
            "failedItems": failed_items,
            "priorityReviewQueue": sorted(
                review_items,
                key=lambda item: (
                    item["confidence"]
                    if item["confidence"]
                       is not None
                    else -1.0
                ),
            ),
            "mostFailedRules": [
                {
                    "ruleNumber": rule_number,
                    "ruleName": RULE_NAMES.get(
                        rule_number,
                        f"Rule {rule_number}",
                    ),
                    "count": count,
                }
                for rule_number, count
                in fail_rule_counts.most_common(10)
            ],
            "mostUncertainRules": [
                {
                    "ruleNumber": rule_number,
                    "ruleName": RULE_NAMES.get(
                        rule_number,
                        f"Rule {rule_number}",
                    ),
                    "count": count,
                }
                for rule_number, count
                in review_rule_counts.most_common(
                    10
                )
            ],
            "documentTypeSummary": (
                document_type_summary
            ),
        }