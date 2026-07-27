# app/services/sweet_engine/context_resolver.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from app.services.sweet_engine.enums import (
    ClassificationSource,
    PageProcessingStatus,
    ReviewPriority,
    ReviewReasonCode,
)
from app.services.sweet_engine.models import PageInventoryItem
from app.services.sweet_engine.page_inventory import PageInventory


@dataclass
class ContextResolutionDecision:
    page_number: int
    resolved: bool
    document_type: str = "UNKNOWN"
    confidence: float = 0.0
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass
class ContextResolverConfig:
    minimum_context_score: float = 0.72
    minimum_raw_confidence: float = 0.40

    previous_page_weight: float = 0.24
    next_page_weight: float = 0.24
    raw_prediction_weight: float = 0.20
    identifier_match_weight: float = 0.18
    text_compatibility_weight: float = 0.14

    conflicting_identifier_penalty: float = 0.35
    neighbour_disagreement_penalty: float = 0.30

    allow_single_neighbour_recovery: bool = True


class ContextResolver:
    def __init__(
        self,
        config: ContextResolverConfig | None = None,
    ) -> None:
        self.config = config or ContextResolverConfig()

    def resolve_inventory(
        self,
        inventory: PageInventory,
    ) -> list[ContextResolutionDecision]:
        """
        Resolve all currently unresolved pages.

        The method deliberately performs one conservative pass.
        Later we can add multiple passes if required.
        """
        decisions: list[ContextResolutionDecision] = []

        for page in inventory.pages:
            if page.is_resolved:
                continue

            decision = self.resolve_page(
                inventory=inventory,
                page=page,
            )

            decisions.append(decision)

            if decision.resolved:
                page.resolve_classification(
                    document_type=decision.document_type,
                    confidence=decision.confidence,
                    source=ClassificationSource.CONTEXT,
                    note=" ".join(decision.reasons),
                )

                page.review.required = False
                page.review.reason_code = None
                page.review.message = ""
                page.review.suggested_action = ""
                page.review.alternatives = []

        return decisions

    def resolve_page(
        self,
        inventory: PageInventory,
        page: PageInventoryItem,
    ) -> ContextResolutionDecision:
        previous_page = inventory.previous_page(
            page.page_number
        )
        next_page = inventory.next_page(
            page.page_number
        )

        candidate_type = self._choose_candidate_type(
            page=page,
            previous_page=previous_page,
            next_page=next_page,
        )

        if candidate_type == "UNKNOWN":
            return self._unresolved_decision(
                page=page,
                message=(
                    "No consistent document type could be derived "
                    "from the page and its neighbours."
                ),
            )

        score = 0.0
        reasons: list[str] = []

        previous_type = self._resolved_type(previous_page)
        next_type = self._resolved_type(next_page)

        # ---------------------------------------------------------
        # Signal 1: previous-page agreement
        # ---------------------------------------------------------
        if previous_type == candidate_type:
            score += self.config.previous_page_weight
            reasons.append(
                f"Previous page {previous_page.page_number} is "
                f"{candidate_type}."
            )

        # ---------------------------------------------------------
        # Signal 2: next-page agreement
        # ---------------------------------------------------------
        if next_type == candidate_type:
            score += self.config.next_page_weight
            reasons.append(
                f"Next page {next_page.page_number} is "
                f"{candidate_type}."
            )

        # ---------------------------------------------------------
        # Signal 3: raw Vision prediction
        # ---------------------------------------------------------
        if (
            page.raw_document_type == candidate_type
            and page.confidence >= self.config.minimum_raw_confidence
        ):
            raw_contribution = (
                self.config.raw_prediction_weight
                * page.confidence
            )
            score += raw_contribution

            reasons.append(
                f"Initial Vision prediction also suggested "
                f"{candidate_type} with confidence "
                f"{page.confidence:.2f}."
            )

        # ---------------------------------------------------------
        # Signal 4: identifier continuity
        # ---------------------------------------------------------
        identifier_score, identifier_reasons = (
            self._identifier_continuity_score(
                current_page=page,
                neighbours=[
                    neighbour
                    for neighbour in (
                        previous_page,
                        next_page,
                    )
                    if neighbour is not None
                ],
            )
        )

        score += (
            self.config.identifier_match_weight
            * identifier_score
        )
        reasons.extend(identifier_reasons)

        # ---------------------------------------------------------
        # Signal 5: text compatibility
        # ---------------------------------------------------------
        text_score, text_reasons = (
            self._text_compatibility_score(
                page=page,
                document_type=candidate_type,
            )
        )

        score += (
            self.config.text_compatibility_weight
            * text_score
        )
        reasons.extend(text_reasons)

        # ---------------------------------------------------------
        # Penalty: neighbours disagree
        # ---------------------------------------------------------
        if (
            previous_type != "UNKNOWN"
            and next_type != "UNKNOWN"
            and previous_type != next_type
        ):
            score -= (
                self.config.neighbour_disagreement_penalty
            )
            reasons.append(
                "Previous and next pages belong to different "
                "document types."
            )

        # ---------------------------------------------------------
        # Penalty: identifier conflict
        # ---------------------------------------------------------
        if self._has_identifier_conflict(
            page=page,
            neighbours=[
                neighbour
                for neighbour in (
                    previous_page,
                    next_page,
                )
                if neighbour is not None
            ],
        ):
            score -= (
                self.config.conflicting_identifier_penalty
            )
            reasons.append(
                "Patient or claim identifiers conflict with "
                "neighbouring pages."
            )

        score = max(0.0, min(1.0, score))

        has_both_neighbours_agreeing = (
            previous_type == candidate_type
            and next_type == candidate_type
        )

        has_one_neighbour_agreeing = (
            previous_type == candidate_type
            or next_type == candidate_type
        )

        neighbour_condition_met = (
            has_both_neighbours_agreeing
            or (
                self.config.allow_single_neighbour_recovery
                and has_one_neighbour_agreeing
                and page.raw_document_type == candidate_type
            )
        )

        if (
            neighbour_condition_met
            and score >= self.config.minimum_context_score
        ):
            confidence = max(
                page.confidence,
                min(0.95, score),
            )

            reasons.append(
                f"Context score {score:.2f} met the automatic "
                f"recovery threshold "
                f"{self.config.minimum_context_score:.2f}."
            )

            return ContextResolutionDecision(
                page_number=page.page_number,
                resolved=True,
                document_type=candidate_type,
                confidence=confidence,
                score=score,
                reasons=reasons,
            )

        return self._unresolved_decision(
            page=page,
            message=(
                f"Context suggested {candidate_type}, but score "
                f"{score:.2f} did not meet the automatic recovery "
                f"threshold "
                f"{self.config.minimum_context_score:.2f}."
            ),
            candidate_type=candidate_type,
            score=score,
            reasons=reasons,
        )

    def _choose_candidate_type(
        self,
        page: PageInventoryItem,
        previous_page: PageInventoryItem | None,
        next_page: PageInventoryItem | None,
    ) -> str:
        previous_type = self._resolved_type(previous_page)
        next_type = self._resolved_type(next_page)

        # Strongest case: both neighbours agree.
        if (
            previous_type != "UNKNOWN"
            and previous_type == next_type
        ):
            return previous_type

        # Raw page prediction agrees with previous.
        if (
            page.raw_document_type != "UNKNOWN"
            and page.raw_document_type == previous_type
        ):
            return page.raw_document_type

        # Raw page prediction agrees with next.
        if (
            page.raw_document_type != "UNKNOWN"
            and page.raw_document_type == next_type
        ):
            return page.raw_document_type

        top_candidate = page.top_candidate()

        if top_candidate:
            candidate_type = top_candidate.document_type

            if candidate_type in {
                previous_type,
                next_type,
            }:
                return candidate_type

        return "UNKNOWN"

    @staticmethod
    def _resolved_type(
        page: PageInventoryItem | None,
    ) -> str:
        if page is None:
            return "UNKNOWN"

        if not page.is_resolved:
            return "UNKNOWN"

        return page.final_document_type

    @staticmethod
    def _identifier_continuity_score(
        current_page: PageInventoryItem,
        neighbours: Iterable[PageInventoryItem],
    ) -> tuple[float, list[str]]:
        current_identifiers = (
            current_page.identifiers.known_values()
        )

        if not current_identifiers:
            return 0.0, []

        comparable = 0
        matched = 0
        reasons: list[str] = []

        for neighbour in neighbours:
            neighbour_identifiers = (
                neighbour.identifiers.known_values()
            )

            for key, current_value in current_identifiers.items():
                neighbour_value = neighbour_identifiers.get(key)

                if not neighbour_value:
                    continue

                comparable += 1

                if ContextResolver._normalize_identifier(
                    current_value
                ) == ContextResolver._normalize_identifier(
                    neighbour_value
                ):
                    matched += 1

                    reasons.append(
                        f"{key} matches page "
                        f"{neighbour.page_number}."
                    )

        if comparable == 0:
            return 0.0, []

        return matched / comparable, reasons

    @staticmethod
    def _has_identifier_conflict(
        page: PageInventoryItem,
        neighbours: Iterable[PageInventoryItem],
    ) -> bool:
        current_identifiers = page.identifiers.known_values()

        strong_keys = {
            "claim_number",
            "mrn",
            "ip_number",
            "bill_number",
        }

        for neighbour in neighbours:
            neighbour_identifiers = (
                neighbour.identifiers.known_values()
            )

            for key in strong_keys:
                current_value = current_identifiers.get(key)
                neighbour_value = neighbour_identifiers.get(key)

                if not current_value or not neighbour_value:
                    continue

                if ContextResolver._normalize_identifier(
                    current_value
                ) != ContextResolver._normalize_identifier(
                    neighbour_value
                ):
                    return True

        return False

    @staticmethod
    def _normalize_identifier(value: str) -> str:
        return "".join(
            character.lower()
            for character in str(value or "")
            if character.isalnum()
        )

    @staticmethod
    def _text_compatibility_score(
        page: PageInventoryItem,
        document_type: str,
    ) -> tuple[float, list[str]]:
        text = (
            page.evidence.extracted_text or ""
        ).lower()

        if not text.strip():
            return 0.0, []

        keyword_map: dict[str, list[str]] = {
            "DISCHARGE_SUMMARY": [
                "diagnosis",
                "hospital course",
                "treatment given",
                "procedure",
                "discharge advice",
                "follow up",
                "condition at discharge",
            ],
            "FINAL_HOSPITAL_BILL": [
                "final bill",
                "total amount",
                "gross amount",
                "net amount",
                "amount payable",
                "bill no",
            ],
            "DETAILED_BILL_BREAKUP": [
                "quantity",
                "rate",
                "amount",
                "service",
                "department",
                "charge",
            ],
            "BILL_CONTINUATION": [
                "quantity",
                "rate",
                "amount",
                "subtotal",
                "carried forward",
                "brought forward",
            ],
            "APPROVAL_LETTER": [
                "approved amount",
                "authorization",
                "cashless",
                "approval",
                "insurer",
                "tpa",
            ],
            "CASHLESS_AUTHORIZATION_LETTER": [
                "cashless authorization",
                "authorization number",
                "approved amount",
                "validity",
                "tpa",
            ],
            "CLAIM_FORM": [
                "claim form",
                "part a",
                "part b",
                "insured",
                "policy number",
                "claim number",
            ],
            "LAB_REPORT": [
                "result",
                "reference range",
                "specimen",
                "test name",
                "laboratory",
            ],
            "RADIOLOGY_REPORT": [
                "findings",
                "impression",
                "radiology",
                "ct scan",
                "mri",
                "ultrasound",
                "x-ray",
            ],
        }

        keywords = keyword_map.get(document_type, [])

        if not keywords:
            return 0.0, []

        matched_keywords = [
            keyword
            for keyword in keywords
            if keyword in text
        ]

        if not matched_keywords:
            return 0.0, []

        score = min(
            1.0,
            len(matched_keywords) / 3,
        )

        return score, [
            "Compatible text indicators found: "
            + ", ".join(matched_keywords[:5])
            + "."
        ]

    @staticmethod
    def _unresolved_decision(
        page: PageInventoryItem,
        message: str,
        candidate_type: str = "UNKNOWN",
        score: float = 0.0,
        reasons: list[str] | None = None,
    ) -> ContextResolutionDecision:
        page.status = PageProcessingStatus.REVIEW_REQUIRED

        page.mark_for_review(
            reason_code=(
                ReviewReasonCode.POSSIBLE_CONTINUATION_PAGE
                if candidate_type != "UNKNOWN"
                else ReviewReasonCode.AMBIGUOUS_DOCUMENT_TYPE
            ),
            message=message,
            suggested_action=(
                "Confirm the correct document type and whether "
                "this page continues the previous or next document."
            ),
            priority=ReviewPriority.MEDIUM,
            alternatives=page.candidates,
        )

        return ContextResolutionDecision(
            page_number=page.page_number,
            resolved=False,
            document_type=candidate_type,
            confidence=page.confidence,
            score=score,
            reasons=reasons or [],
        )