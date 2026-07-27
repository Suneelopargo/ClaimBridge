# app/services/sweet_engine/boundary_resolver.py

from __future__ import annotations

from app.services.sweet_engine.boundary_evidence_collector import (
    BoundaryEvidence,
    BoundaryEvidenceCollector,
    BoundarySignal,
)
from app.services.sweet_engine.boundary_reasoner import (
    BoundaryDecision,
    BoundaryReasoner,
    BoundaryType,
)
from app.services.sweet_engine.page_inventory import PageInventory


class BoundaryResolver:
    """Backward-compatible facade for the two-stage boundary pipeline."""

    def __init__(
        self,
        *,
        evidence_collector: BoundaryEvidenceCollector | None = None,
        reasoner: BoundaryReasoner | None = None,
    ) -> None:
        self.evidence_collector = evidence_collector or BoundaryEvidenceCollector()
        self.reasoner = reasoner or BoundaryReasoner()

    def resolve_inventory(self, inventory: PageInventory) -> list[BoundaryDecision]:
        evidence_items = self.evidence_collector.collect_inventory(inventory)
        return self.reasoner.reason_inventory(
            inventory=inventory,
            evidence_items=evidence_items,
        )


__all__ = [
    "BoundaryDecision",
    "BoundaryEvidence",
    "BoundaryEvidenceCollector",
    "BoundaryReasoner",
    "BoundaryResolver",
    "BoundarySignal",
    "BoundaryType",
]
