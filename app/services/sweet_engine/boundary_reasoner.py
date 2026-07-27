# app/services/sweet_engine/boundary_reasoner.py

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.services.sweet_engine.boundary_evidence_collector import BoundaryEvidence, BoundarySignal
from app.services.sweet_engine.page_inventory import PageInventory


class BoundaryType(str, Enum):
    START = "START"
    CONTINUATION = "CONTINUATION"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


@dataclass
class BoundaryDecision:
    page_number: int
    boundary_type: BoundaryType
    score: int
    confidence: float
    reasons: list[str] = field(default_factory=list)
    signals: list[BoundarySignal] = field(default_factory=list)
    start_score: int = 0
    continuation_score: int = 0


class BoundaryReasoner:
    """Reason over previous/current/next evidence and decide boundaries."""

    START_MARGIN = 35
    CONTINUATION_MARGIN = 25

    def reason_inventory(
        self,
        *,
        inventory: PageInventory,
        evidence_items: list[BoundaryEvidence],
    ) -> list[BoundaryDecision]:
        decisions: list[BoundaryDecision] = []

        for index, evidence in enumerate(evidence_items):
            previous_evidence = evidence_items[index - 1] if index > 0 else None
            next_evidence = evidence_items[index + 1] if index + 1 < len(evidence_items) else None
            decision = self.reason_page(
                evidence=evidence,
                previous_evidence=previous_evidence,
                next_evidence=next_evidence,
            )
            decisions.append(decision)
            self._apply_decision(inventory.get_page(decision.page_number), decision)

        return decisions

    def reason_page(
        self,
        *,
        evidence: BoundaryEvidence,
        previous_evidence: BoundaryEvidence | None,
        next_evidence: BoundaryEvidence | None,
    ) -> BoundaryDecision:
        if evidence.previous_page_number is None:
            return BoundaryDecision(
                page_number=evidence.page_number,
                boundary_type=BoundaryType.START,
                score=100,
                confidence=1.0,
                reasons=["First packet page always starts a group."],
                signals=evidence.signals,
                start_score=evidence.start_score,
                continuation_score=evidence.continuation_score,
            )

        start_score = evidence.start_score
        continuation_score = evidence.continuation_score
        reasons = [signal.reason for signal in evidence.signals]

        if (
            evidence.current_type == "UNKNOWN"
            and next_evidence is not None
            and self._is_strong_start(next_evidence)
            and evidence.previous_family != "UNKNOWN"
        ):
            continuation_score += 40
            reasons.append(
                "Three-page reasoning: unknown page precedes a strong next-document start and likely continues the previous document."
            )

        if (
            evidence.detected_title_type
            and evidence.current_family == evidence.previous_family
            and continuation_score >= 45
        ):
            start_score = max(0, start_score - 35)
            reasons.append(
                "Repeated title was discounted because stronger continuation evidence exists within the same family."
            )

        if (
            next_evidence is not None
            and evidence.current_family != "UNKNOWN"
            and evidence.current_family == next_evidence.current_family
            and not self._is_strong_start(next_evidence)
            and evidence.current_family == evidence.previous_family
        ):
            continuation_score += 15
            reasons.append(
                "Three-page family continuity supports keeping the current page with adjacent pages."
            )

        if (
            evidence.detected_title_type
            and next_evidence is not None
            and next_evidence.current_family == evidence.current_family
            and next_evidence.continuation_score > next_evidence.start_score
        ):
            start_score += 15
            reasons.append(
                "Current explicit title is followed by a compatible continuation page."
            )

        margin = start_score - continuation_score
        if margin >= self.START_MARGIN:
            boundary_type = BoundaryType.START
        elif margin <= -self.CONTINUATION_MARGIN:
            boundary_type = BoundaryType.CONTINUATION
        else:
            boundary_type = BoundaryType.AMBIGUOUS

        return BoundaryDecision(
            page_number=evidence.page_number,
            boundary_type=boundary_type,
            score=margin,
            confidence=self._confidence(margin, boundary_type),
            reasons=reasons,
            signals=evidence.signals,
            start_score=start_score,
            continuation_score=continuation_score,
        )

    @staticmethod
    def _is_strong_start(evidence: BoundaryEvidence) -> bool:
        return evidence.start_score - evidence.continuation_score >= 45

    @staticmethod
    def _confidence(margin: int, boundary_type: BoundaryType) -> float:
        absolute_margin = abs(margin)
        if boundary_type == BoundaryType.AMBIGUOUS:
            return max(0.50, min(0.69, 0.50 + absolute_margin / 200))
        return min(0.99, 0.70 + absolute_margin / 150)

    @staticmethod
    def _apply_decision(page: Any, decision: BoundaryDecision) -> None:
        page.boundary_type = decision.boundary_type.value
        page.evidence.custom_features["boundaryEvidence"] = {
            "startScore": decision.start_score,
            "continuationScore": decision.continuation_score,
            "netScore": decision.score,
            "signals": [
                {
                    "code": signal.code,
                    "direction": signal.direction,
                    "weight": signal.weight,
                    "reason": signal.reason,
                }
                for signal in decision.signals
            ],
        }
        page.evidence.custom_features["boundaryDecision"] = {
            "boundaryType": decision.boundary_type.value,
            "score": decision.score,
            "confidence": decision.confidence,
            "reasons": decision.reasons,
        }
        page.add_processing_note(
            f"Boundary {decision.boundary_type.value}: start={decision.start_score}, continuation={decision.continuation_score}, net={decision.score}, confidence={decision.confidence:.2f}."
        )
