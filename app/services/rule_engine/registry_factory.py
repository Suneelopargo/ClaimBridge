# app/services/rule_engine/registry_factory.py

from __future__ import annotations

from app.services.rule_engine.operators.document_exists import (
    DocumentExistsOperator,
)

from app.services.rule_engine.operator_registry import (
    OperatorRegistry,
)


def build_default_operator_registry(
) -> OperatorRegistry:
    registry = OperatorRegistry()

    document_exists = DocumentExistsOperator()

    registry.register(
        "DOCUMENT_EXISTS",
        document_exists,
    )

    # These aliases protect us if the seeded rule type uses
    # slightly different naming.
    registry.register(
        "DOCUMENT_REQUIRED",
        document_exists,
    )

    registry.register(
        "CHECKLIST_DOCUMENT",
        document_exists,
    )

    return registry