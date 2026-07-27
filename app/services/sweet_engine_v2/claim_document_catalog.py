# app/services/sweet_engine_v2/claim_document_catalog.py

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class RequirementLevel(str, Enum):
    REQUIRED = "REQUIRED"
    CONDITIONAL = "CONDITIONAL"
    OPTIONAL = "OPTIONAL"


class DocumentCardinality(str, Enum):
    SINGLE = "SINGLE"
    MULTIPLE = "MULTIPLE"


@dataclass(frozen=True)
class ClaimDocumentDefinition:
    code: str
    display_name: str
    family: str
    requirement: RequirementLevel = RequirementLevel.OPTIONAL
    cardinality: DocumentCardinality = DocumentCardinality.MULTIPLE
    standalone: bool = False
    continuation_of: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    notes: str = ""

    @property
    def is_continuation(self) -> bool:
        return bool(self.continuation_of)


def _definition(
    code: str,
    display_name: str,
    family: str,
    *,
    requirement: RequirementLevel = RequirementLevel.OPTIONAL,
    cardinality: DocumentCardinality = DocumentCardinality.MULTIPLE,
    standalone: bool = False,
    continuation_of: tuple[str, ...] = (),
    aliases: tuple[str, ...] = (),
    notes: str = "",
) -> ClaimDocumentDefinition:
    return ClaimDocumentDefinition(
        code=code,
        display_name=display_name,
        family=family,
        requirement=requirement,
        cardinality=cardinality,
        standalone=standalone,
        continuation_of=continuation_of,
        aliases=aliases,
        notes=notes,
    )


DOCUMENT_CATALOG: dict[str, ClaimDocumentDefinition] = {
    "UNKNOWN": _definition(
        "UNKNOWN",
        "Unknown Document",
        "UNKNOWN",
        notes="Unclassified page or document.",
    ),

    # Correspondence
    "COVERING_LETTER": _definition(
        "COVERING_LETTER",
        "Covering Letter",
        "CORRESPONDENCE",
        cardinality=DocumentCardinality.SINGLE,
        standalone=True,
        aliases=("COVER LETTER", "FORWARDING LETTER"),
    ),
    "JUSTIFICATION_LETTER": _definition(
        "JUSTIFICATION_LETTER",
        "Justification Letter",
        "CORRESPONDENCE",
        aliases=("JUSTIFICATION", "JUSTIFICATION NOTE", "MEDICAL JUSTIFICATION"),
    ),
    "QUERY_LETTER": _definition(
        "QUERY_LETTER",
        "Insurer / TPA Query Letter",
        "CORRESPONDENCE",
        aliases=("QUERY", "DEFICIENCY LETTER", "REQUIREMENT LETTER"),
    ),
    "QUERY_RESPONSE": _definition(
        "QUERY_RESPONSE",
        "Query Response",
        "CORRESPONDENCE",
        aliases=("REPLY TO QUERY", "QUERY REPLY", "DEFICIENCY RESPONSE"),
    ),

    # Authorization
    "CASHLESS_AUTHORIZATION_LETTER": _definition(
        "CASHLESS_AUTHORIZATION_LETTER",
        "Cashless Authorization Letter",
        "AUTHORIZATION",
        requirement=RequirementLevel.CONDITIONAL,
        aliases=(
            "CASHLESS AUTHORISATION LETTER",
            "AUTHORIZATION LETTER",
            "AUTHORISATION LETTER",
            "INITIAL PRE AUTHORIZATION APPROVAL",
            "FINAL PRE AUTHORIZATION APPROVAL",
        ),
    ),
    "INITIAL_AUTHORIZATION": _definition(
        "INITIAL_AUTHORIZATION",
        "Initial Authorization",
        "AUTHORIZATION",
        aliases=("INITIAL APPROVAL", "INITIAL CASHLESS APPROVAL"),
    ),
    "FINAL_AUTHORIZATION": _definition(
        "FINAL_AUTHORIZATION",
        "Final Authorization",
        "AUTHORIZATION",
        aliases=("FINAL APPROVAL", "FINAL CASHLESS APPROVAL"),
    ),
    "GOP_PRE_APPROVAL": _definition(
        "GOP_PRE_APPROVAL",
        "GOP / Pre-Approval",
        "AUTHORIZATION",
        aliases=("GOP", "GUARANTEE OF PAYMENT", "PRE APPROVAL"),
    ),
    "GOP_FINAL_APPROVAL": _definition(
        "GOP_FINAL_APPROVAL",
        "GOP Final Approval",
        "AUTHORIZATION",
    ),
    "ENHANCEMENT_REQUEST": _definition(
        "ENHANCEMENT_REQUEST",
        "Enhancement Request",
        "AUTHORIZATION",
    ),
    "ENHANCEMENT_APPROVAL": _definition(
        "ENHANCEMENT_APPROVAL",
        "Enhancement Approval",
        "AUTHORIZATION",
    ),
    "DENIAL_LETTER": _definition(
        "DENIAL_LETTER",
        "Denial / Rejection Letter",
        "AUTHORIZATION",
        aliases=("REJECTION LETTER", "REPUDIATION LETTER"),
    ),
    "AUTHORIZATION_CONTINUATION": _definition(
        "AUTHORIZATION_CONTINUATION",
        "Authorization Continuation",
        "AUTHORIZATION",
        continuation_of=(
            "CASHLESS_AUTHORIZATION_LETTER",
            "INITIAL_AUTHORIZATION",
            "FINAL_AUTHORIZATION",
            "GOP_PRE_APPROVAL",
            "GOP_FINAL_APPROVAL",
            "ENHANCEMENT_REQUEST",
            "ENHANCEMENT_APPROVAL",
            "QUERY_LETTER",
            "QUERY_RESPONSE",
        ),
    ),

    # Preauthorization / forms
    "PREAUTHORIZATION_FORM": _definition(
        "PREAUTHORIZATION_FORM",
        "Preauthorization Form",
        "PREAUTHORIZATION",
        requirement=RequirementLevel.CONDITIONAL,
        aliases=(
            "PREAUTH FORM",
            "PRE-AUTHORIZATION FORM",
            "REQUEST FOR CASHLESS HOSPITALISATION",
            "REQUEST FOR CASHLESS HOSPITALIZATION",
        ),
    ),
    "CLAIM_FORM": _definition(
        "CLAIM_FORM",
        "Claim Form",
        "CLAIM_FORM",
        requirement=RequirementLevel.CONDITIONAL,
    ),
    "FORM_CONTINUATION": _definition(
        "FORM_CONTINUATION",
        "Form Continuation",
        "PREAUTHORIZATION",
        continuation_of=("PREAUTHORIZATION_FORM", "CLAIM_FORM"),
    ),
    "CHECKLIST": _definition(
        "CHECKLIST",
        "Dispatch Checklist",
        "CHECKLIST",
        cardinality=DocumentCardinality.SINGLE,
        standalone=True,
        aliases=("DESPATCH CHECKLIST", "DISPATCH CHECKLIST"),
    ),

    # Billing / financial
    "FINAL_HOSPITAL_BILL": _definition(
        "FINAL_HOSPITAL_BILL",
        "Final Hospital Bill",
        "BILL",
        requirement=RequirementLevel.REQUIRED,
        aliases=("FINAL BILL", "INPATIENT BILL", "IN PATIENT BILL", "CREDIT BILL"),
    ),
    "DETAILED_BILL": _definition(
        "DETAILED_BILL",
        "Detailed Bill",
        "BILL",
        requirement=RequirementLevel.CONDITIONAL,
        aliases=("DETAILED BILL BREAKUP", "ITEMIZED BILL", "ITEMISED BILL"),
    ),
    "BILL_SUMMARY": _definition(
        "BILL_SUMMARY",
        "Bill Summary",
        "BILL",
    ),
    "BILL_CONTINUATION": _definition(
        "BILL_CONTINUATION",
        "Bill Continuation",
        "BILL",
        continuation_of=("FINAL_HOSPITAL_BILL", "DETAILED_BILL", "BILL_SUMMARY"),
    ),
    "PAYMENT_RECEIPT": _definition(
        "PAYMENT_RECEIPT",
        "Payment Receipt",
        "PAYMENT",
        standalone=True,
        aliases=("DEPOSIT RECEIPT", "MONEY RECEIPT", "PAYMENT VOUCHER"),
    ),
    "ADVANCE_RECEIPT": _definition(
        "ADVANCE_RECEIPT",
        "Advance Receipt",
        "PAYMENT",
        standalone=True,
    ),
    "REFUND_RECEIPT": _definition(
        "REFUND_RECEIPT",
        "Refund Receipt",
        "PAYMENT",
        standalone=True,
    ),

    # Clinical
    "DISCHARGE_SUMMARY": _definition(
        "DISCHARGE_SUMMARY",
        "Discharge Summary",
        "DISCHARGE_SUMMARY",
        requirement=RequirementLevel.REQUIRED,
        aliases=("DISCHARGE ADVICE",),
    ),
    "DISCHARGE_SUMMARY_CONTINUATION": _definition(
        "DISCHARGE_SUMMARY_CONTINUATION",
        "Discharge Summary Continuation",
        "DISCHARGE_SUMMARY",
        continuation_of=("DISCHARGE_SUMMARY",),
    ),
    "DOCTOR_PRESCRIPTION": _definition(
        "DOCTOR_PRESCRIPTION",
        "Doctor Prescription",
        "CLINICAL_ORDER",
        requirement=RequirementLevel.CONDITIONAL,
        aliases=("PRESCRIPTION", "MEDICAL PRESCRIPTION", "DOCTOR ADVICE"),
    ),
    "TREATMENT_ORDER": _definition(
        "TREATMENT_ORDER",
        "Treatment Order",
        "CLINICAL_ORDER",
        requirement=RequirementLevel.CONDITIONAL,
        aliases=(
            "CHEMOTHERAPY ORDER FORM",
            "CHEMO THERAPY ORDER FORM",
            "RADIOTHERAPY ORDER FORM",
            "SURGERY ORDER FORM",
            "TREATMENT PLAN",
        ),
    ),
    "CONSULTATION_NOTE": _definition(
        "CONSULTATION_NOTE",
        "Consultation Note",
        "CLINICAL_RECORD",
    ),
    "OPERATIVE_NOTE": _definition(
        "OPERATIVE_NOTE",
        "Operative Note",
        "CLINICAL_RECORD",
        requirement=RequirementLevel.CONDITIONAL,
        aliases=("OT NOTE", "OT NOTES", "OPERATION NOTE"),
    ),
    "ANESTHESIA_RECORD": _definition(
        "ANESTHESIA_RECORD",
        "Anesthesia Record",
        "CLINICAL_RECORD",
        requirement=RequirementLevel.CONDITIONAL,
    ),
    "NURSING_RECORD": _definition(
        "NURSING_RECORD",
        "Nursing Record",
        "CLINICAL_RECORD",
    ),
    "PROGRESS_NOTE": _definition(
        "PROGRESS_NOTE",
        "Progress Note",
        "CLINICAL_RECORD",
    ),
    "CASE_PAPER": _definition(
        "CASE_PAPER",
        "Case Paper",
        "CLINICAL_RECORD",
    ),

    # Investigation
    "LAB_REPORT": _definition(
        "LAB_REPORT",
        "Laboratory Report",
        "INVESTIGATION",
        requirement=RequirementLevel.CONDITIONAL,
        aliases=("LABORATORY REPORT", "BLOOD REPORT"),
    ),
    "PATHOLOGY_REPORT": _definition(
        "PATHOLOGY_REPORT",
        "Pathology Report",
        "INVESTIGATION",
        requirement=RequirementLevel.CONDITIONAL,
        aliases=("HISTOPATHOLOGY REPORT", "BIOPSY REPORT"),
    ),
    "RADIOLOGY_REPORT": _definition(
        "RADIOLOGY_REPORT",
        "Radiology Report",
        "INVESTIGATION",
        requirement=RequirementLevel.CONDITIONAL,
        aliases=("CT REPORT", "MRI REPORT", "X-RAY REPORT", "ULTRASOUND REPORT"),
    ),
    "DIAGNOSTIC_REPORT": _definition(
        "DIAGNOSTIC_REPORT",
        "Diagnostic Report",
        "INVESTIGATION",
        requirement=RequirementLevel.CONDITIONAL,
    ),
    "ECG_REPORT": _definition(
        "ECG_REPORT",
        "ECG Report",
        "INVESTIGATION",
        requirement=RequirementLevel.CONDITIONAL,
    ),
    "INVESTIGATION_REPORT": _definition(
        "INVESTIGATION_REPORT",
        "Investigation Report",
        "INVESTIGATION",
        requirement=RequirementLevel.CONDITIONAL,
    ),

    # Pharmacy / consumables
    "PHARMACY_BILL": _definition(
        "PHARMACY_BILL",
        "Pharmacy Bill",
        "PHARMACY",
        requirement=RequirementLevel.CONDITIONAL,
        aliases=("MEDICINE BILL", "PHARMACY INVOICE", "DRUG BILL"),
    ),
    "PHARMACY_REPORT": _definition(
        "PHARMACY_REPORT",
        "Pharmacy Report",
        "PHARMACY",
        requirement=RequirementLevel.CONDITIONAL,
    ),
    "MEDICINE_INVOICE": _definition(
        "MEDICINE_INVOICE",
        "Medicine Invoice",
        "PHARMACY",
        requirement=RequirementLevel.CONDITIONAL,
    ),
    "MEDICINE_ADMINISTRATION_RECORD": _definition(
        "MEDICINE_ADMINISTRATION_RECORD",
        "Medicine Administration Record",
        "PHARMACY_RECORD",
        requirement=RequirementLevel.CONDITIONAL,
        aliases=("MAR", "DRUG ADMINISTRATION CHART"),
    ),
    "IMPLANT_INVOICE": _definition(
        "IMPLANT_INVOICE",
        "Implant Invoice",
        "CONSUMABLE",
        requirement=RequirementLevel.CONDITIONAL,
    ),
    "CONSUMABLES_INVOICE": _definition(
        "CONSUMABLES_INVOICE",
        "Consumables Invoice",
        "CONSUMABLE",
        requirement=RequirementLevel.CONDITIONAL,
    ),

    # Consent / declaration
    "GENERAL_CONSENT_FORM": _definition(
        "GENERAL_CONSENT_FORM",
        "General Consent Form",
        "CONSENT",
        requirement=RequirementLevel.CONDITIONAL,
        aliases=("CONSENT FORM", "GENERAL CONSENT"),
    ),
    "SURGERY_CONSENT_FORM": _definition(
        "SURGERY_CONSENT_FORM",
        "Surgery Consent Form",
        "CONSENT",
        requirement=RequirementLevel.CONDITIONAL,
    ),
    "ANESTHESIA_CONSENT_FORM": _definition(
        "ANESTHESIA_CONSENT_FORM",
        "Anesthesia Consent Form",
        "CONSENT",
        requirement=RequirementLevel.CONDITIONAL,
    ),
    "PROCEDURE_CONSENT_FORM": _definition(
        "PROCEDURE_CONSENT_FORM",
        "Procedure Consent Form",
        "CONSENT",
        requirement=RequirementLevel.CONDITIONAL,
    ),
    "BLOOD_TRANSFUSION_CONSENT": _definition(
        "BLOOD_TRANSFUSION_CONSENT",
        "Blood Transfusion Consent",
        "CONSENT",
        requirement=RequirementLevel.CONDITIONAL,
    ),
    "HIGH_RISK_CONSENT": _definition(
        "HIGH_RISK_CONSENT",
        "High-Risk Consent",
        "CONSENT",
        requirement=RequirementLevel.CONDITIONAL,
    ),
    "PATIENT_DECLARATION": _definition(
        "PATIENT_DECLARATION",
        "Patient Declaration",
        "DECLARATION",
        requirement=RequirementLevel.CONDITIONAL,
    ),
    "GIPSA_DECLARATION": _definition(
        "GIPSA_DECLARATION",
        "GIPSA / PPN Declaration",
        "DECLARATION",
        requirement=RequirementLevel.CONDITIONAL,
        standalone=True,
        aliases=("PPN DECLARATION", "PPN NETWORK DECLARATION"),
    ),

    # Identity / insurance
    "PATIENT_ID_PROOF": _definition(
        "PATIENT_ID_PROOF",
        "Patient ID Proof",
        "PATIENT_ID",
        requirement=RequirementLevel.REQUIRED,
        standalone=True,
        aliases=("PATIENT AADHAAR", "PATIENT AADHAR", "PATIENT PAN"),
    ),
    "PROPOSER_ID_PROOF": _definition(
        "PROPOSER_ID_PROOF",
        "Proposer ID Proof",
        "PROPOSER_ID",
        requirement=RequirementLevel.CONDITIONAL,
        standalone=True,
        aliases=("PROPOSER AADHAAR", "PROPOSER AADHAR", "PROPOSER PAN"),
    ),
    "ATTENDANT_ID_PROOF": _definition(
        "ATTENDANT_ID_PROOF",
        "Attendant ID Proof",
        "ATTENDANT_ID",
        standalone=True,
    ),
    "INSURANCE_CARD": _definition(
        "INSURANCE_CARD",
        "Insurance / Health Card",
        "INSURANCE_ID",
        requirement=RequirementLevel.REQUIRED,
        standalone=True,
        aliases=("HEALTH CARD", "TPA CARD", "MEMBER CARD", "E-CARD"),
    ),
    "POLICY_DOCUMENT": _definition(
        "POLICY_DOCUMENT",
        "Policy Document",
        "INSURANCE_POLICY",
        requirement=RequirementLevel.CONDITIONAL,
    ),
    "EMPLOYEE_ID_CARD": _definition(
        "EMPLOYEE_ID_CARD",
        "Employee ID Card",
        "EMPLOYEE_ID",
        requirement=RequirementLevel.CONDITIONAL,
        standalone=True,
    ),
}


# These pairs must never be grouped into one logical document merely because
# pages are adjacent or share patient/claim identifiers.
HARD_SEPARATION_PAIRS: frozenset[frozenset[str]] = frozenset(
    {
        frozenset({"JUSTIFICATION_LETTER", "LAB_REPORT"}),
        frozenset({"JUSTIFICATION_LETTER", "PATHOLOGY_REPORT"}),
        frozenset({"JUSTIFICATION_LETTER", "RADIOLOGY_REPORT"}),
        frozenset({"JUSTIFICATION_LETTER", "INVESTIGATION_REPORT"}),
        frozenset({"PATIENT_ID_PROOF", "PROPOSER_ID_PROOF"}),
        frozenset({"PATIENT_ID_PROOF", "INSURANCE_CARD"}),
        frozenset({"PROPOSER_ID_PROOF", "INSURANCE_CARD"}),
        frozenset({"PHARMACY_BILL", "DOCTOR_PRESCRIPTION"}),
        frozenset({"PHARMACY_REPORT", "DOCTOR_PRESCRIPTION"}),
        frozenset({"FINAL_HOSPITAL_BILL", "PAYMENT_RECEIPT"}),
        frozenset({"DETAILED_BILL", "PAYMENT_RECEIPT"}),
        frozenset({"SURGERY_CONSENT_FORM", "ANESTHESIA_CONSENT_FORM"}),
        frozenset({"GENERAL_CONSENT_FORM", "SURGERY_CONSENT_FORM"}),
        frozenset({"GENERAL_CONSENT_FORM", "ANESTHESIA_CONSENT_FORM"}),
        frozenset({"COVERING_LETTER", "JUSTIFICATION_LETTER"}),
    }
)


def _normalise_token(value: str) -> str:
    value = str(value or "").strip().upper()
    value = re.sub(r"[^A-Z0-9]+", "_", value)
    return value.strip("_") or "UNKNOWN"


_ALIAS_TO_CODE: dict[str, str] = {}

for _code, _item in DOCUMENT_CATALOG.items():
    _ALIAS_TO_CODE[_normalise_token(_code)] = _code
    _ALIAS_TO_CODE[_normalise_token(_item.display_name)] = _code

    for _alias in _item.aliases:
        _ALIAS_TO_CODE[_normalise_token(_alias)] = _code


# Compatibility aliases from the current sweet_engine registry/output.
_COMPATIBILITY_ALIASES = {
    "DETAILED_BILL_BREAKUP": "DETAILED_BILL",
    "CONSENT_FORM": "GENERAL_CONSENT_FORM",
    "PRESCRIPTION": "DOCTOR_PRESCRIPTION",
    "OT_NOTES": "OPERATIVE_NOTE",
    "KYC_DOCUMENT": "PATIENT_ID_PROOF",
}

for _alias, _code in _COMPATIBILITY_ALIASES.items():
    _ALIAS_TO_CODE[_normalise_token(_alias)] = _code


def normalize_document_type(value: str | None) -> str:
    return _ALIAS_TO_CODE.get(_normalise_token(value or "UNKNOWN"), _normalise_token(value or "UNKNOWN"))


def definition_for(value: str | None) -> ClaimDocumentDefinition:
    code = normalize_document_type(value)

    return DOCUMENT_CATALOG.get(
        code,
        ClaimDocumentDefinition(
            code=code,
            display_name=code.replace("_", " ").title(),
            family="OTHER",
        ),
    )


def document_family(value: str | None) -> str:
    return definition_for(value).family


def display_name(value: str | None) -> str:
    return definition_for(value).display_name


def is_standalone(value: str | None) -> bool:
    return definition_for(value).standalone


def is_continuation(value: str | None) -> bool:
    return definition_for(value).is_continuation


def continuation_parent_types(value: str | None) -> tuple[str, ...]:
    return definition_for(value).continuation_of


def can_continue(parent_type: str | None, continuation_type: str | None) -> bool:
    parent = normalize_document_type(parent_type)
    continuation = definition_for(continuation_type)
    return continuation.is_continuation and parent in continuation.continuation_of


def hard_separation(left_type: str | None, right_type: str | None) -> bool:
    left = normalize_document_type(left_type)
    right = normalize_document_type(right_type)

    if left == right:
        return False

    if frozenset({left, right}) in HARD_SEPARATION_PAIRS:
        return True

    # Identity roles and consent subtypes are distinct logical documents.
    left_family = document_family(left)
    right_family = document_family(right)

    if left_family in {"PATIENT_ID", "PROPOSER_ID", "ATTENDANT_ID", "INSURANCE_ID", "EMPLOYEE_ID"}:
        return left_family != right_family

    if left_family == right_family == "CONSENT":
        return left != right

    return False


def compatible_bucket_types(page_type: str | None) -> tuple[str, ...]:
    page_code = normalize_document_type(page_type)
    item = definition_for(page_code)

    if item.is_continuation:
        return item.continuation_of

    # A normal page may only join an existing bucket of exactly the same
    # canonical type. Family equality alone is intentionally insufficient.
    return (page_code,)


def catalog_codes() -> tuple[str, ...]:
    return tuple(DOCUMENT_CATALOG.keys())


def iter_definitions() -> Iterable[ClaimDocumentDefinition]:
    return DOCUMENT_CATALOG.values()


__all__ = [
    "ClaimDocumentDefinition",
    "DocumentCardinality",
    "DOCUMENT_CATALOG",
    "HARD_SEPARATION_PAIRS",
    "RequirementLevel",
    "can_continue",
    "catalog_codes",
    "compatible_bucket_types",
    "continuation_parent_types",
    "definition_for",
    "display_name",
    "document_family",
    "hard_separation",
    "is_continuation",
    "is_standalone",
    "iter_definitions",
    "normalize_document_type",
]
