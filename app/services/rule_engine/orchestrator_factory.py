# app/services/rule_engine/orchestrator_factory.py

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.rule_engine.registry_factory import (
    build_default_operator_registry,
)
from app.services.rule_engine.rule_execution_service import (
    RuleExecutionService,
)
from app.services.rule_engine.rule_executor import RuleExecutor
from app.services.rule_engine.rule_loader import RuleLoader
from app.services.rule_engine.validation_orchestrator import (
    ValidationOrchestrator,
)
from app.services.rule_engine.validation_run_repository import (
    ValidationRunRepository,
)


def build_validation_orchestrator(
    db: Session,
) -> ValidationOrchestrator:
    registry = build_default_operator_registry()

    executor = RuleExecutor(
        operator_registry=registry
    )

    execution_service = RuleExecutionService(
        rule_executor=executor
    )

    return ValidationOrchestrator(
        db=db,
        rule_loader=RuleLoader(db),
        execution_service=execution_service,
        repository=ValidationRunRepository(db),
    )