# app/services/sweet_engine/boundary_evidence_collector.py

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.sweet_engine.models import PageInventoryItem
from app.services.sweet_engine.page_inventory import PageInventory


@dataclass
class BoundarySignal:
    code: str
    direction: str
    weight: int
    reason: str


@dataclass
class BoundaryEvidence:
    page_number: int
    previous_page_number: int | None
    next_page_number: int | None
    start_score: int = 0
    continuation_score: int = 0
    signals: list[BoundarySignal] = field(default_factory=list)
    detected_title_type: str | None = None
    current_type: str = "UNKNOWN"
    previous_type: str = "UNKNOWN"
    next_type: str = "UNKNOWN"
    current_family: str = "UNKNOWN"
    previous_family: str = "UNKNOWN"
    next_family: str = "UNKNOWN"

    @property
    def net_score(self) -> int:
        return self.start_score - self.continuation_score


class BoundaryEvidenceCollector:
    """Collect boundary evidence without making the final decision."""

    DOCUMENT_FAMILIES = {
        "CASHLESS_AUTHORIZATION_LETTER": "AUTHORIZATION",
        "PREAUTHORIZATION_FORM": "PREAUTHORIZATION",
        "FINAL_HOSPITAL_BILL": "BILL",
        "BILL_CONTINUATION": "BILL",
        "PAYMENT_RECEIPT": "PAYMENT",
        "TREATMENT_ORDER": "TREATMENT_ORDER",
        "CHEMO_THERAPY_ORDER_FORM": "TREATMENT_ORDER",
        "CHEMOTHERAPY_ORDER_FORM": "TREATMENT_ORDER",
        "DISCHARGE_SUMMARY": "DISCHARGE_SUMMARY",
        "PATIENT_ID_PROOF": "PATIENT_ID",
        "PROPOSER_ID_PROOF": "PROPOSER_ID",
        "CHECKLIST": "CHECKLIST",
        "COVERING_LETTER": "COVERING_LETTER",
        "GIPSA_DECLARATION": "DECLARATION",
    }

    TITLE_PATTERNS = {
        "CHECKLIST": ("despatch checklist", "dispatch checklist"),
        "CASHLESS_AUTHORIZATION_LETTER": ("cashless authorization letter",),
        "PREAUTHORIZATION_FORM": (
            "request for cashless hospitalisation",
            "request for cashless hospitalization",
        ),
        "GIPSA_DECLARATION": (
            "ppn network",
            "declaration by patient",
            "declaration regarding insurance policy",
        ),
        "FINAL_HOSPITAL_BILL": (
            "final hospital bill",
            "final bill",
            "detailed bill",
        ),
        "PAYMENT_RECEIPT": ("deposit receipt", "payment receipt"),
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

    CONTINUATION_PATTERNS = (
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

    LIKELY_STANDALONE_TYPES = {
        "COVERING_LETTER",
        "CHECKLIST",
        "GIPSA_DECLARATION",
        "PAYMENT_RECEIPT",
    }

    def collect_inventory(self, inventory: PageInventory) -> list[BoundaryEvidence]:
        pages = sorted(inventory.pages, key=lambda page: page.page_number)
        items: list[BoundaryEvidence] = []

        for index, current_page in enumerate(pages):
            previous_page = pages[index - 1] if index > 0 else None
            next_page = pages[index + 1] if index + 1 < len(pages) else None
            items.append(
                self.collect_page(
                    previous_page=previous_page,
                    current_page=current_page,
                    next_page=next_page,
                )
            )

        return items

    def collect_page(
        self,
        *,
        previous_page: PageInventoryItem | None,
        current_page: PageInventoryItem,
        next_page: PageInventoryItem | None,
    ) -> BoundaryEvidence:
        current_type = self._normalize_document_type(current_page.final_document_type)
        previous_type = self._normalize_document_type(
            previous_page.final_document_type if previous_page else "UNKNOWN"
        )
        next_type = self._normalize_document_type(
            next_page.final_document_type if next_page else "UNKNOWN"
        )

        item = BoundaryEvidence(
            page_number=current_page.page_number,
            previous_page_number=previous_page.page_number if previous_page else None,
            next_page_number=next_page.page_number if next_page else None,
            current_type=current_type,
            previous_type=previous_type,
            next_type=next_type,
            current_family=self._document_family(current_type),
            previous_family=self._document_family(previous_type),
            next_family=self._document_family(next_type),
        )

        if previous_page is None:
            self._add_start(item, "FIRST_PACKET_PAGE", 100, "First packet page always starts a group.")
            return item

        previous_text = self._normalize_text(previous_page.evidence.extracted_text)
        current_text = self._normalize_text(current_page.evidence.extracted_text)
        next_text = self._normalize_text(
            next_page.evidence.extracted_text if next_page else ""
        )

        title_type = self._detect_title(current_text)
        item.detected_title_type = title_type

        if title_type:
            self._add_start(
                item,
                "EXPLICIT_TITLE_IN_HEADER",
                65,
                f"Explicit document title detected in the header region: {title_type}.",
            )
            if title_type == current_type:
                self._add_start(
                    item,
                    "TITLE_MATCHES_CLASSIFICATION",
                    10,
                    "Detected header title agrees with the current page classification.",
                )

        if item.current_family != item.previous_family:
            self._add_start(
                item,
                "DOCUMENT_FAMILY_CHANGE",
                30,
                f"Document family changed from {item.previous_family} to {item.current_family}.",
            )
        else:
            self._add_continuation(
                item,
                "SAME_DOCUMENT_FAMILY",
                20,
                "Current and previous pages belong to the same document family.",
            )

        if current_type != previous_type and item.current_family == item.previous_family:
            self._add_start(
                item,
                "TYPE_CHANGE_WITHIN_FAMILY",
                5,
                f"Type changed from {previous_type} to {current_type} inside the same family.",
            )

        self._collect_page_number_signals(item, previous_text, current_text)
        self._collect_identifier_signals(item, previous_page, current_page)

        if self._contains_any(current_text, *self.CONTINUATION_PATTERNS):
            self._add_continuation(
                item,
                "CONTINUATION_LANGUAGE",
                30,
                "Current page contains continuation, appendix or authorization-continuation language.",
            )

        if self._same_strong_identifiers(previous_page, current_page):
            self._add_continuation(
                item,
                "SAME_STRONG_IDENTIFIERS",
                20,
                "Current and previous pages share strong claim or bill identifiers.",
            )

        if self._header_changed(previous_text, current_text):
            self._add_start(
                item,
                "WEAK_HEADER_CHANGE",
                5,
                "Header token pattern changed; this is only a weak supporting signal.",
            )

        if (
            current_type == "UNKNOWN"
            and item.previous_family != "UNKNOWN"
            and item.next_family != item.previous_family
            and self._detect_title(next_text)
        ):
            self._add_continuation(
                item,
                "UNKNOWN_BEFORE_STRONG_NEXT_START",
                35,
                "Unknown page is followed by a strong new-document start, so it likely continues the previous group.",
            )

        if current_type in self.LIKELY_STANDALONE_TYPES and item.current_family != item.previous_family:
            self._add_start(
                item,
                "LIKELY_STANDALONE_DOCUMENT",
                15,
                f"{current_type} is usually a standalone document instance.",
            )

        return item

    def _collect_page_number_signals(self, item: BoundaryEvidence, previous_text: str, current_text: str) -> None:
        previous_number = self._extract_page_number(previous_text)
        current_number = self._extract_page_number(current_text)

        if current_number and current_number[0] == 1:
            self._add_start(item, "PAGE_NUMBER_RESTART", 30, "Current page numbering restarts at page 1.")

        if not previous_number or not current_number:
            return

        previous_current, previous_total = previous_number
        current_current, current_total = current_number

        if current_current == previous_current + 1 and (
            previous_total is None
            or current_total is None
            or previous_total == current_total
        ):
            self._add_continuation(
                item,
                "SEQUENTIAL_PAGE_NUMBER",
                60,
                "Current page number sequentially follows the previous page.",
            )

    def _collect_identifier_signals(
        self,
        item: BoundaryEvidence,
        previous_page: PageInventoryItem,
        current_page: PageInventoryItem,
    ) -> None:
        comparisons = (
            ("CLAIM_NUMBER", previous_page.identifiers.claim_number, current_page.identifiers.claim_number, 15),
            ("BILL_NUMBER", previous_page.identifiers.bill_number, current_page.identifiers.bill_number, 20),
            ("PATIENT_NAME", previous_page.identifiers.patient_name, current_page.identifiers.patient_name, 8),
        )

        for code, previous_value, current_value, weight in comparisons:
            previous_normalized = self._normalize_identifier(previous_value)
            current_normalized = self._normalize_identifier(current_value)
            if previous_normalized and current_normalized and previous_normalized != current_normalized:
                self._add_start(
                    item,
                    f"{code}_CHANGE",
                    weight,
                    f"{code.lower()} changed between adjacent pages.",
                )

        previous_date = self._normalize_identifier(previous_page.financial_metadata.document_date)
        current_date = self._normalize_identifier(current_page.financial_metadata.document_date)
        if previous_date and current_date and previous_date != current_date:
            self._add_start(item, "DOCUMENT_DATE_CHANGE", 8, "Document date changed between adjacent pages.")

        previous_amount = self._normalize_identifier(previous_page.financial_metadata.total_amount)
        current_amount = self._normalize_identifier(current_page.financial_metadata.total_amount)
        if previous_amount and current_amount and previous_amount != current_amount:
            self._add_start(item, "TOTAL_AMOUNT_CHANGE", 8, "Document amount changed between adjacent pages.")

    def _detect_title(self, text: str) -> str | None:
        title_zone = self._header_zone(text)
        for document_type, patterns in self.TITLE_PATTERNS.items():
            if self._contains_any(title_zone, *patterns):
                return document_type
        return None

    @staticmethod
    def _header_zone(text: str) -> str:
        if not text:
            return ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return " ".join(lines[:18])[:650] if lines else text[:650]

    @staticmethod
    def _extract_page_number(text: str) -> tuple[int, int | None] | None:
        for pattern in (
            r"\bpage\s+(\d+)\s+of\s+(\d+)\b",
            r"\bpage\s*[:\-]?\s*(\d+)\s*/\s*(\d+)\b",
        ):
            match = re.search(pattern, text)
            if match:
                return int(match.group(1)), int(match.group(2))
        return None

    def _same_strong_identifiers(self, previous_page: PageInventoryItem, current_page: PageInventoryItem) -> bool:
        previous_claim = self._normalize_identifier(previous_page.identifiers.claim_number)
        current_claim = self._normalize_identifier(current_page.identifiers.claim_number)
        if previous_claim and current_claim and previous_claim == current_claim:
            return True

        previous_bill = self._normalize_identifier(previous_page.identifiers.bill_number)
        current_bill = self._normalize_identifier(current_page.identifiers.bill_number)
        return bool(previous_bill and current_bill and previous_bill == current_bill)

    def _header_changed(self, previous_text: str, current_text: str) -> bool:
        previous_tokens = self._header_tokens(previous_text)
        current_tokens = self._header_tokens(current_text)
        if len(previous_tokens) < 3 or len(current_tokens) < 3:
            return False
        union = previous_tokens | current_tokens
        similarity = len(previous_tokens & current_tokens) / len(union) if union else 1.0
        return similarity < 0.10

    def _header_tokens(self, text: str) -> set[str]:
        tokens = re.findall(r"[a-z0-9]{4,}", self._header_zone(text))
        stop_words = {"patient", "hospital", "insurance", "health", "details", "name", "date", "page", "form"}
        return {token for token in tokens if token not in stop_words}

    def _document_family(self, document_type: str) -> str:
        return self.DOCUMENT_FAMILIES.get(document_type, document_type)

    @staticmethod
    def _normalize_document_type(value: Any) -> str:
        normalized = re.sub(r"[\s\-]+", "_", str(value or "UNKNOWN").strip().upper())
        return {
            "CHEMO_THERAPY_ORDER_FORM": "TREATMENT_ORDER",
            "CHEMOTHERAPY_ORDER_FORM": "TREATMENT_ORDER",
        }.get(normalized, normalized)

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return str(value or "").lower().replace("\r\n", "\n").replace("\r", "\n").strip()

    @staticmethod
    def _normalize_identifier(value: Any) -> str:
        return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

    @staticmethod
    def _contains_any(text: str, *phrases: str) -> bool:
        return any(phrase in text for phrase in phrases)

    @staticmethod
    def _add_start(item: BoundaryEvidence, code: str, weight: int, reason: str) -> None:
        item.start_score += weight
        item.signals.append(BoundarySignal(code=code, direction="START", weight=weight, reason=reason))

    @staticmethod
    def _add_continuation(item: BoundaryEvidence, code: str, weight: int, reason: str) -> None:
        item.continuation_score += weight
        item.signals.append(BoundarySignal(code=code, direction="CONTINUATION", weight=weight, reason=reason))
