# app/services/sweet_engine/document_registry.py

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class PageRole(str, Enum):
    START = "START"
    CONTINUATION = "CONTINUATION"
    END = "END"
    STANDALONE = "STANDALONE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DocumentDefinition:
    document_type: str
    family: str
    standalone: bool
    can_start_group: bool = True
    can_continue_group: bool = False
    aliases: tuple[str, ...] = ()


DOCUMENT_REGISTRY: dict[str, DocumentDefinition] = {
    "UNKNOWN": DocumentDefinition(
        "UNKNOWN", "UNKNOWN", False, False, False
    ),

    # Correspondence
    "COVERING_LETTER": DocumentDefinition(
        "COVERING_LETTER",
        "CORRESPONDENCE",
        True,
        aliases=("COVER LETTER", "FORWARDING LETTER"),
    ),
    "JUSTIFICATION_LETTER": DocumentDefinition(
        "JUSTIFICATION_LETTER",
        "CORRESPONDENCE",
        True,
        aliases=("JUSTIFICATION", "JUSTIFICATION NOTE"),
    ),
    "APPROVAL_LETTER": DocumentDefinition(
        "APPROVAL_LETTER",
        "AUTHORIZATION",
        True,
    ),
    "GOP_PRE_APPROVAL": DocumentDefinition(
        "GOP_PRE_APPROVAL",
        "AUTHORIZATION",
        True,
    ),
    "GOP_FINAL_APPROVAL": DocumentDefinition(
        "GOP_FINAL_APPROVAL",
        "AUTHORIZATION",
        True,
    ),

    # Authorization / preauthorization
    "CASHLESS_AUTHORIZATION_LETTER": DocumentDefinition(
        "CASHLESS_AUTHORIZATION_LETTER",
        "AUTHORIZATION",
        False,
        True,
        True,
        aliases=(
            "CASHLESS AUTHORISATION LETTER",
            "FINAL PRE AUTHORIZATION APPROVAL",
            "FINAL PRE-AUTHORIZATION APPROVAL",
            "INITIAL PRE AUTHORIZATION APPROVAL",
            "INITIAL PRE-AUTHORIZATION APPROVAL",
        ),
    ),
    "AUTHORIZATION_CONTINUATION": DocumentDefinition(
        "AUTHORIZATION_CONTINUATION",
        "AUTHORIZATION",
        False,
        False,
        True,
    ),
    "PREAUTHORIZATION_FORM": DocumentDefinition(
        "PREAUTHORIZATION_FORM",
        "PREAUTHORIZATION",
        False,
        True,
        True,
        aliases=(
            "PREAUTH FORM",
            "PRE-AUTHORIZATION FORM",
            "REQUEST FOR CASHLESS HOSPITALISATION",
            "REQUEST FOR CASHLESS HOSPITALIZATION",
        ),
    ),
    "FORM_CONTINUATION": DocumentDefinition(
        "FORM_CONTINUATION",
        "PREAUTHORIZATION",
        False,
        False,
        True,
    ),

    # Claim and declaration forms
    "CLAIM_FORM": DocumentDefinition(
        "CLAIM_FORM",
        "CLAIM_FORM",
        False,
        True,
        True,
    ),
    "GIPSA_DECLARATION": DocumentDefinition(
        "GIPSA_DECLARATION",
        "DECLARATION",
        True,
        aliases=(
            "PPN DECLARATION",
            "PPN NETWORK DECLARATION",
        ),
    ),
    "CHECKLIST": DocumentDefinition(
        "CHECKLIST",
        "CHECKLIST",
        True,
        aliases=("DESPATCH CHECKLIST", "DISPATCH CHECKLIST"),
    ),

    # Billing and payments
    "FINAL_HOSPITAL_BILL": DocumentDefinition(
        "FINAL_HOSPITAL_BILL",
        "BILL",
        False,
        True,
        True,
        aliases=(
            "FINAL BILL",
            "IN PATIENT BILL",
            "IN-PATIENT BILL",
            "CREDIT BILL",
            "BILL OF SUPPLY",
        ),
    ),
    "DETAILED_BILL_BREAKUP": DocumentDefinition(
        "DETAILED_BILL_BREAKUP",
        "BILL",
        False,
        True,
        True,
    ),
    "BILL_CONTINUATION": DocumentDefinition(
        "BILL_CONTINUATION",
        "BILL",
        False,
        False,
        True,
    ),
    "PAYMENT_RECEIPT": DocumentDefinition(
        "PAYMENT_RECEIPT",
        "PAYMENT",
        True,
        aliases=(
            "DEPOSIT ADJUSTED RECEIPT",
            "PAYMENT VOUCHER",
        ),
    ),
    "REFUND_RECEIPT": DocumentDefinition(
        "REFUND_RECEIPT",
        "PAYMENT",
        True,
    ),

    # Identity and KYC
    "KYC_DOCUMENT": DocumentDefinition(
        "KYC_DOCUMENT",
        "IDENTITY",
        True,
    ),
    "PATIENT_ID_PROOF": DocumentDefinition(
        "PATIENT_ID_PROOF",
        "IDENTITY",
        True,
    ),
    "PROPOSER_ID_PROOF": DocumentDefinition(
        "PROPOSER_ID_PROOF",
        "IDENTITY",
        True,
    ),
    "INSURANCE_CARD": DocumentDefinition(
        "INSURANCE_CARD",
        "IDENTITY",
        True,
        aliases=("MEMBER CARD", "HEALTH CARD", "TPA CARD"),
    ),
    "PATIENT_PHOTO": DocumentDefinition(
        "PATIENT_PHOTO",
        "IDENTITY",
        True,
    ),

    # Clinical documents
    "DISCHARGE_SUMMARY": DocumentDefinition(
        "DISCHARGE_SUMMARY",
        "DISCHARGE_SUMMARY",
        False,
        True,
        True,
    ),
    "DISCHARGE_SUMMARY_CONTINUATION": DocumentDefinition(
        "DISCHARGE_SUMMARY_CONTINUATION",
        "DISCHARGE_SUMMARY",
        False,
        False,
        True,
    ),
    "TREATMENT_ORDER": DocumentDefinition(
        "TREATMENT_ORDER",
        "CLINICAL_ORDER",
        False,
        True,
        True,
        aliases=(
            "CHEMO THERAPY ORDER FORM",
            "CHEMOTHERAPY ORDER FORM",
            "TREATMENT PLAN",
            "CYBERKNIFE TREATMENT CARD",
        ),
    ),
    "CASE_PAPER": DocumentDefinition(
        "CASE_PAPER",
        "CLINICAL_RECORD",
        False,
        True,
        True,
    ),
    "OT_NOTES": DocumentDefinition(
        "OT_NOTES",
        "CLINICAL_RECORD",
        False,
        True,
        True,
    ),
    "CONSENT_FORM": DocumentDefinition(
        "CONSENT_FORM",
        "CONSENT",
        False,
        True,
        True,
    ),
    "PRESCRIPTION": DocumentDefinition(
        "PRESCRIPTION",
        "CLINICAL_ORDER",
        True,
    ),

    # Reports
    "INVESTIGATION_REPORT": DocumentDefinition(
        "INVESTIGATION_REPORT",
        "INVESTIGATION",
        False,
        True,
        True,
    ),
    "LAB_REPORT": DocumentDefinition(
        "LAB_REPORT",
        "INVESTIGATION",
        False,
        True,
        True,
    ),
    "RADIOLOGY_REPORT": DocumentDefinition(
        "RADIOLOGY_REPORT",
        "INVESTIGATION",
        False,
        True,
        True,
    ),

    # Pharmacy / consumables
    "PHARMACY_BILL": DocumentDefinition(
        "PHARMACY_BILL",
        "PHARMACY",
        False,
        True,
        True,
    ),
    "PHARMACY_DETAILS": DocumentDefinition(
        "PHARMACY_DETAILS",
        "PHARMACY",
        False,
        True,
        True,
    ),
    "IMPLANT_STICKER_INVOICE": DocumentDefinition(
        "IMPLANT_STICKER_INVOICE",
        "IMPLANT",
        False,
        True,
        True,
    ),
    "BLOOD_COMPONENT_STICKER": DocumentDefinition(
        "BLOOD_COMPONENT_STICKER",
        "BLOOD_COMPONENT",
        False,
        True,
        True,
    ),
    "NON_MEDICAL_DETAILS": DocumentDefinition(
        "NON_MEDICAL_DETAILS",
        "BILL",
        False,
        True,
        True,
    ),
}


def normalize_token(value: Any) -> str:
    text = str(value or "").strip().upper()
    text = re.sub(r"[\s\-\/]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


_ALIAS_TO_TYPE: dict[str, str] = {}

for canonical_type, definition in DOCUMENT_REGISTRY.items():
    _ALIAS_TO_TYPE[normalize_token(canonical_type)] = canonical_type

    for alias in definition.aliases:
        _ALIAS_TO_TYPE[normalize_token(alias)] = canonical_type


def normalize_document_type(value: Any) -> str:
    token = normalize_token(value)
    return _ALIAS_TO_TYPE.get(token, "UNKNOWN")


def is_supported_document_type(value: Any) -> bool:
    return normalize_document_type(value) != "UNKNOWN"


def document_family(value: Any) -> str:
    canonical = normalize_document_type(value)
    return DOCUMENT_REGISTRY[canonical].family


def is_standalone_document(value: Any) -> bool:
    canonical = normalize_document_type(value)
    return DOCUMENT_REGISTRY[canonical].standalone


def can_start_group(value: Any) -> bool:
    canonical = normalize_document_type(value)
    return DOCUMENT_REGISTRY[canonical].can_start_group


def can_continue_group(value: Any) -> bool:
    canonical = normalize_document_type(value)
    return DOCUMENT_REGISTRY[canonical].can_continue_group


def allowed_document_types() -> list[str]:
    return sorted(DOCUMENT_REGISTRY.keys())


def normalize_page_role(value: Any) -> str:
    token = normalize_token(value)

    aliases = {
        "FIRST": PageRole.START.value,
        "FIRST_PAGE": PageRole.START.value,
        "DOCUMENT_START": PageRole.START.value,
        "MIDDLE": PageRole.CONTINUATION.value,
        "CONTINUE": PageRole.CONTINUATION.value,
        "DOCUMENT_CONTINUATION": PageRole.CONTINUATION.value,
        "LAST": PageRole.END.value,
        "LAST_PAGE": PageRole.END.value,
        "DOCUMENT_END": PageRole.END.value,
        "SINGLE": PageRole.STANDALONE.value,
        "SINGLE_PAGE": PageRole.STANDALONE.value,
    }

    if token in {role.value for role in PageRole}:
        return token

    return aliases.get(token, PageRole.UNKNOWN.value)


__all__ = [
    "DOCUMENT_REGISTRY",
    "DocumentDefinition",
    "PageRole",
    "allowed_document_types",
    "can_continue_group",
    "can_start_group",
    "document_family",
    "is_standalone_document",
    "is_supported_document_type",
    "normalize_document_type",
    "normalize_page_role",
    "normalize_token",
]
