# app/services/sweet_engine/document_identity_resolver.py

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from app.services.sweet_engine.models import PageInventoryItem
from app.services.sweet_engine.page_inventory import PageInventory


class IdentityRelation(str, Enum):
    FIRST_PAGE = "FIRST_PAGE"
    SAME_DOCUMENT = "SAME_DOCUMENT"
    NEW_DOCUMENT = "NEW_DOCUMENT"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class IdentitySignal:
    code: str
    direction: str
    weight: int
    reason: str


@dataclass
class DocumentFingerprint:
    page_number: int
    document_type: str
    document_family: str
    title_type: str | None = None
    header_signature: str | None = None
    template_signature: str | None = None
    patient_name: str | None = None
    claim_number: str | None = None
    authorization_number: str | None = None
    bill_number: str | None = None
    policy_number: str | None = None
    member_id: str | None = None
    document_date: str | None = None
    printed_page_number: int | None = None
    printed_total_pages: int | None = None
    identity_key: str | None = None


@dataclass
class DocumentIdentityDecision:
    page_number: int
    previous_page_number: int | None
    relation: IdentityRelation
    same_document_score: int
    new_document_score: int
    net_score: int
    confidence: float
    fingerprint: DocumentFingerprint
    signals: list[IdentitySignal] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    identity_chain_id: str | None = None


class DocumentIdentityResolver:
    """Resolve provisional document identity continuity between pages."""

    SAME_DOCUMENT_MARGIN = 25
    NEW_DOCUMENT_MARGIN = 35

    DOCUMENT_FAMILIES = {
        "CASHLESS_AUTHORIZATION_LETTER": "AUTHORIZATION",
        "PREAUTHORIZATION_FORM": "PREAUTHORIZATION",
        "FINAL_HOSPITAL_BILL": "BILL",
        "BILL_CONTINUATION": "BILL",
        "PAYMENT_RECEIPT": "PAYMENT",
        "TREATMENT_ORDER": "TREATMENT_ORDER",
        "CHEMO_THERAPY_ORDER_FORM": "TREATMENT_ORDER",
        "CHEMOTHERAPY_ORDER_FORM": "TREATMENT_ORDER",
        "RADIATION_THERAPY_ORDER": "TREATMENT_ORDER",
        "SURGERY_ORDER": "TREATMENT_ORDER",
        "DISCHARGE_SUMMARY": "DISCHARGE_SUMMARY",
        "PATIENT_ID_PROOF": "PATIENT_ID",
        "PROPOSER_ID_PROOF": "PROPOSER_ID",
        "CHECKLIST": "CHECKLIST",
        "COVERING_LETTER": "COVERING_LETTER",
        "GIPSA_DECLARATION": "DECLARATION",
    }

    TITLE_PATTERNS = {
        "CHECKLIST": ("despatch checklist", "dispatch checklist"),
        "CASHLESS_AUTHORIZATION_LETTER": (
            "cashless authorization letter",
            "authorization letter",
        ),
        "PREAUTHORIZATION_FORM": (
            "request for cashless hospitalisation",
            "request for cashless hospitalization",
            "pre authorization request",
            "pre-authorisation request",
        ),
        "GIPSA_DECLARATION": (
            "gipsa declaration",
            "declaration by patient",
            "ppn declaration",
        ),
        "FINAL_HOSPITAL_BILL": (
            "final hospital bill",
            "final bill",
            "detailed hospital bill",
        ),
        "PAYMENT_RECEIPT": (
            "deposit receipt",
            "payment receipt",
            "money receipt",
        ),
        "TREATMENT_ORDER": (
            "chemotherapy order form",
            "chemo therapy order form",
            "radiotherapy order form",
            "radiation therapy order form",
            "surgery order form",
            "treatment order form",
        ),
        "DISCHARGE_SUMMARY": ("discharge summary", "discharge advice"),
    }

    LIKELY_STANDALONE_TYPES = {
        "COVERING_LETTER",
        "CHECKLIST",
        "GIPSA_DECLARATION",
        "PAYMENT_RECEIPT",
    }

    def resolve_inventory(self, inventory: PageInventory) -> list[DocumentIdentityDecision]:
        pages = sorted(inventory.pages, key=lambda page: page.page_number)
        fingerprints = {
            page.page_number: self.build_fingerprint(page)
            for page in pages
        }

        decisions: list[DocumentIdentityDecision] = []
        current_chain_number = 0
        current_chain_id: str | None = None

        for index, current_page in enumerate(pages):
            current_fingerprint = fingerprints[current_page.page_number]

            if index == 0:
                current_chain_number += 1
                current_chain_id = self._make_chain_id(
                    inventory.packet_id,
                    current_chain_number,
                )
                decision = DocumentIdentityDecision(
                    page_number=current_page.page_number,
                    previous_page_number=None,
                    relation=IdentityRelation.FIRST_PAGE,
                    same_document_score=0,
                    new_document_score=100,
                    net_score=100,
                    confidence=1.0,
                    fingerprint=current_fingerprint,
                    signals=[
                        IdentitySignal(
                            code="FIRST_PACKET_PAGE",
                            direction="NEW_DOCUMENT",
                            weight=100,
                            reason="First packet page begins the first identity chain.",
                        )
                    ],
                    reasons=["First packet page begins the first identity chain."],
                    identity_chain_id=current_chain_id,
                )
            else:
                previous_page = pages[index - 1]
                decision = self.compare_pages(
                    previous_page=previous_page,
                    current_page=current_page,
                    previous_fingerprint=fingerprints[previous_page.page_number],
                    current_fingerprint=current_fingerprint,
                )
                if decision.relation == IdentityRelation.NEW_DOCUMENT:
                    current_chain_number += 1
                    current_chain_id = self._make_chain_id(
                        inventory.packet_id,
                        current_chain_number,
                    )
                decision.identity_chain_id = current_chain_id

            decisions.append(decision)
            self._apply_decision(page=current_page, decision=decision)

        return decisions

    def compare_pages(
        self,
        *,
        previous_page: PageInventoryItem,
        current_page: PageInventoryItem,
        previous_fingerprint: DocumentFingerprint,
        current_fingerprint: DocumentFingerprint,
    ) -> DocumentIdentityDecision:
        signals: list[IdentitySignal] = []
        same_score = 0
        new_score = 0

        def add_same(code: str, weight: int, reason: str) -> None:
            nonlocal same_score
            same_score += weight
            signals.append(IdentitySignal(code, "SAME_DOCUMENT", weight, reason))

        def add_new(code: str, weight: int, reason: str) -> None:
            nonlocal new_score
            new_score += weight
            signals.append(IdentitySignal(code, "NEW_DOCUMENT", weight, reason))

        if previous_fingerprint.document_family == current_fingerprint.document_family:
            add_same(
                "SAME_DOCUMENT_FAMILY",
                25,
                "Adjacent pages belong to the same normalized document family.",
            )
        else:
            add_new(
                "DOCUMENT_FAMILY_CHANGE",
                35,
                "Normalized document family changed between adjacent pages.",
            )

        comparisons = (
            ("CLAIM_NUMBER", previous_fingerprint.claim_number, current_fingerprint.claim_number, 30, 35),
            ("AUTHORIZATION_NUMBER", previous_fingerprint.authorization_number, current_fingerprint.authorization_number, 45, 55),
            ("BILL_NUMBER", previous_fingerprint.bill_number, current_fingerprint.bill_number, 40, 50),
            ("POLICY_NUMBER", previous_fingerprint.policy_number, current_fingerprint.policy_number, 20, 25),
            ("MEMBER_ID", previous_fingerprint.member_id, current_fingerprint.member_id, 20, 25),
            ("PATIENT_NAME", previous_fingerprint.patient_name, current_fingerprint.patient_name, 15, 20),
        )

        for code, previous_value, current_value, same_weight, new_weight in comparisons:
            self._compare_identifier(
                previous_value,
                current_value,
                code=code,
                same_weight=same_weight,
                new_weight=new_weight,
                add_same=add_same,
                add_new=add_new,
            )

        if self._is_sequential_page_number(previous_fingerprint, current_fingerprint):
            add_same(
                "SEQUENTIAL_PRINTED_PAGE_NUMBER",
                65,
                "Printed page numbering continues sequentially.",
            )
        elif (
            current_fingerprint.printed_page_number == 1
            and previous_fingerprint.printed_page_number not in (None, 0)
        ):
            add_new(
                "PRINTED_PAGE_NUMBER_RESTART",
                45,
                "Printed page numbering restarts at page 1.",
            )

        if (
            previous_fingerprint.template_signature
            and previous_fingerprint.template_signature == current_fingerprint.template_signature
        ):
            add_same(
                "SAME_TEMPLATE_SIGNATURE",
                30,
                "Header/template signature matches the previous page.",
            )

        if (
            previous_fingerprint.header_signature
            and previous_fingerprint.header_signature == current_fingerprint.header_signature
        ):
            add_same(
                "SAME_HEADER_SIGNATURE",
                20,
                "Normalized header signature matches the previous page.",
            )

        if (
            current_fingerprint.title_type
            and current_fingerprint.title_type == previous_fingerprint.title_type
            and current_fingerprint.document_family == previous_fingerprint.document_family
        ):
            add_same(
                "REPEATED_TITLE_WITHIN_FAMILY",
                20,
                "Repeated title is treated as running-header evidence.",
            )

        if (
            current_fingerprint.title_type
            and current_fingerprint.title_type != previous_fingerprint.title_type
            and self._document_family(current_fingerprint.title_type)
            != previous_fingerprint.document_family
        ):
            add_new(
                "NEW_HEADER_TITLE",
                45,
                "A different explicit title appears in the current page header.",
            )

        current_text = self._normalize_text(current_page.evidence.extracted_text)
        if self._has_continuation_language(current_text):
            add_same(
                "CONTINUATION_LANGUAGE",
                30,
                "Current page contains continuation or carried-forward language.",
            )

        if (
            current_fingerprint.document_type in self.LIKELY_STANDALONE_TYPES
            and previous_fingerprint.document_family != current_fingerprint.document_family
        ):
            add_new(
                "LIKELY_STANDALONE_TYPE",
                15,
                "Current type is usually a standalone document.",
            )

        net_score = new_score - same_score
        if net_score >= self.NEW_DOCUMENT_MARGIN:
            relation = IdentityRelation.NEW_DOCUMENT
        elif net_score <= -self.SAME_DOCUMENT_MARGIN:
            relation = IdentityRelation.SAME_DOCUMENT
        else:
            relation = IdentityRelation.UNCERTAIN

        return DocumentIdentityDecision(
            page_number=current_page.page_number,
            previous_page_number=previous_page.page_number,
            relation=relation,
            same_document_score=same_score,
            new_document_score=new_score,
            net_score=net_score,
            confidence=self._confidence(relation=relation, net_score=net_score),
            fingerprint=current_fingerprint,
            signals=signals,
            reasons=[signal.reason for signal in signals],
        )

    def build_fingerprint(self, page: PageInventoryItem) -> DocumentFingerprint:
        document_type = self._normalize_document_type(page.final_document_type)
        document_family = self._document_family(document_type)
        text = self._normalize_text(page.evidence.extracted_text)
        header_zone = self._header_zone(text)
        printed_page_number, printed_total_pages = (
            self._extract_page_number(text)
        )

        if printed_page_number is None:
            printed_page_number = self._safe_int(
                self._custom_feature(
                    page,
                    "printedPageNumber",
                )
                or self._custom_feature(
                    page,
                    "printed_page_number",
                )
            )

        if printed_total_pages is None:
            printed_total_pages = self._safe_int(
                self._custom_feature(
                    page,
                    "printedTotalPages",
                )
                or self._custom_feature(
                    page,
                    "printed_total_pages",
                )
            )
        title_type = self._detect_title(header_zone)
        identifiers = page.identifiers
        metadata = page.financial_metadata

        patient_name = self._normalize_identifier(getattr(identifiers, "patient_name", None))
        claim_number = self._normalize_identifier(getattr(identifiers, "claim_number", None))
        authorization_number = self._first_normalized_value(
            getattr(identifiers, "authorization_number", None),
            self._custom_feature(page, "authorization_number"),
            self._custom_feature(page, "authorizationNumber"),
            self._custom_feature(page, "preauth_number"),
        )
        bill_number = self._normalize_identifier(getattr(identifiers, "bill_number", None))
        policy_number = self._first_normalized_value(
            getattr(identifiers, "policy_number", None),
            self._custom_feature(page, "policy_number"),
            self._custom_feature(page, "policyNumber"),
        )
        member_id = self._first_normalized_value(
            getattr(identifiers, "member_id", None),
            self._custom_feature(page, "member_id"),
            self._custom_feature(page, "memberId"),
            self._custom_feature(page, "uhid"),
        )
        document_date = self._normalize_identifier(getattr(metadata, "document_date", None))

        header_signature = self._signature(self._header_tokens(header_zone))
        template_signature = self._signature(self._template_tokens(header_zone))

        identity_components = [
            document_family,
            title_type or "",
            patient_name or "",
            claim_number or "",
            authorization_number or "",
            bill_number or "",
            policy_number or "",
            member_id or "",
            template_signature or "",
        ]
        identity_key = hashlib.sha1("|".join(identity_components).encode("utf-8")).hexdigest()[:16]

        return DocumentFingerprint(
            page_number=page.page_number,
            document_type=document_type,
            document_family=document_family,
            title_type=title_type,
            header_signature=header_signature,
            template_signature=template_signature,
            patient_name=patient_name,
            claim_number=claim_number,
            authorization_number=authorization_number,
            bill_number=bill_number,
            policy_number=policy_number,
            member_id=member_id,
            document_date=document_date,
            printed_page_number=printed_page_number,
            printed_total_pages=printed_total_pages,
            identity_key=identity_key,
        )

    @staticmethod
    def _compare_identifier(previous_value: str | None, current_value: str | None, *, code: str, same_weight: int, new_weight: int, add_same: Any, add_new: Any) -> None:
        if not previous_value or not current_value:
            return
        if previous_value == current_value:
            add_same(f"SAME_{code}", same_weight, f"{code.lower()} matches the previous page.")
        else:
            add_new(f"{code}_CHANGE", new_weight, f"{code.lower()} changed between adjacent pages.")

    @staticmethod
    def _is_sequential_page_number(previous: DocumentFingerprint, current: DocumentFingerprint) -> bool:
        if previous.printed_page_number is None or current.printed_page_number is None:
            return False
        if current.printed_page_number != previous.printed_page_number + 1:
            return False
        return (
            previous.printed_total_pages is None
            or current.printed_total_pages is None
            or previous.printed_total_pages == current.printed_total_pages
        )

    def _detect_title(self, header_zone: str) -> str | None:
        for document_type, patterns in self.TITLE_PATTERNS.items():
            if any(pattern in header_zone for pattern in patterns):
                return document_type
        return None

    @staticmethod
    def _has_continuation_language(text: str) -> bool:
        phrases = (
            "continued",
            "continuation",
            "contd",
            "carried forward",
            "brought forward",
            "terms and conditions for authorization",
            "authorization summary",
            "authorization remarks",
            "appendix 1",
            "appendix 2",
        )
        return any(phrase in text for phrase in phrases)

    @staticmethod
    def _extract_page_number(text: str) -> tuple[int | None, int | None]:
        patterns = (
            r"\bpage\s+(\d+)\s+of\s+(\d+)\b",
            r"\bpage\s*[:\-]?\s*(\d+)\s*/\s*(\d+)\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return int(match.group(1)), int(match.group(2))
        return None, None

    @staticmethod
    def _header_zone(text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return " ".join(lines[:18])[:650] if lines else text[:650]

    @staticmethod
    def _header_tokens(text: str) -> list[str]:
        tokens = re.findall(r"[a-z0-9]{4,}", text)
        stop_words = {"patient", "hospital", "insurance", "health", "details", "name", "date", "page", "form", "number"}
        return sorted({token for token in tokens if token not in stop_words})[:30]

    @staticmethod
    def _template_tokens(text: str) -> list[str]:
        normalized = re.sub(r"\b\d{1,4}([/\-.]\d{1,4})+\b", " ", text)
        normalized = re.sub(r"\b\d{4,}\b", " ", normalized)
        normalized = re.sub(r"\b(?:rs|inr)\.?\s*[\d,]+(?:\.\d+)?\b", " ", normalized)
        return DocumentIdentityResolver._header_tokens(normalized)

    @staticmethod
    def _signature(tokens: list[str]) -> str | None:
        return hashlib.sha1("|".join(tokens).encode("utf-8")).hexdigest()[:16] if tokens else None

    def _document_family(self, document_type: str) -> str:
        return self.DOCUMENT_FAMILIES.get(document_type, document_type)

    @staticmethod
    def _normalize_document_type(value: Any) -> str:
        normalized = re.sub(r"[\s\-]+", "_", str(value or "UNKNOWN").strip().upper())
        aliases = {
            "CHEMO_THERAPY_ORDER_FORM": "TREATMENT_ORDER",
            "CHEMOTHERAPY_ORDER_FORM": "TREATMENT_ORDER",
        }
        return aliases.get(normalized, normalized)

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return str(value or "").lower().replace("\r\n", "\n").replace("\r", "\n").strip()

    @staticmethod
    def _normalize_identifier(value: Any) -> str | None:
        normalized = re.sub(r"[^a-z0-9]", "", str(value or "").lower())
        return normalized or None

    def _first_normalized_value(self, *values: Any) -> str | None:
        for value in values:
            normalized = self._normalize_identifier(value)
            if normalized:
                return normalized
        return None

    @staticmethod
    def _custom_feature(page: PageInventoryItem, key: str) -> Any:
        return (getattr(page.evidence, "custom_features", {}) or {}).get(key)

    @staticmethod
    def _confidence(*, relation: IdentityRelation, net_score: int) -> float:
        absolute_score = abs(net_score)
        if relation == IdentityRelation.UNCERTAIN:
            return max(0.50, min(0.69, 0.50 + absolute_score / 200))
        return min(0.99, 0.70 + absolute_score / 160)

    @staticmethod
    def _make_chain_id(packet_id: Any, chain_number: int) -> str:
        return f"{str(packet_id or 'packet')}-identity-{chain_number:03d}"

    @staticmethod
    def _apply_decision(*, page: PageInventoryItem, decision: DocumentIdentityDecision) -> None:
        features = page.evidence.custom_features
        features["documentFingerprint"] = asdict(decision.fingerprint)
        features["documentIdentity"] = {
            "relation": decision.relation.value,
            "previousPageNumber": decision.previous_page_number,
            "sameDocumentScore": decision.same_document_score,
            "newDocumentScore": decision.new_document_score,
            "netScore": decision.net_score,
            "confidence": decision.confidence,
            "identityChainId": decision.identity_chain_id,
            "signals": [asdict(signal) for signal in decision.signals],
            "reasons": decision.reasons,
        }
        page.add_processing_note(
            "Document identity: "
            f"{decision.relation.value}, "
            f"same={decision.same_document_score}, "
            f"new={decision.new_document_score}, "
            f"net={decision.net_score}, "
            f"confidence={decision.confidence:.2f}, "
            f"chain={decision.identity_chain_id}."
        )

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        if value in (None, ""):
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None


__all__ = [
    "DocumentFingerprint",
    "DocumentIdentityDecision",
    "DocumentIdentityResolver",
    "IdentityRelation",
    "IdentitySignal",
]
