from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.models.base import Base


class ClaimValidationResult(Base):
    __tablename__ = "claim_validation_result"

    id = Column(Integer, primary_key=True, index=True)

    validation_run_id = Column(
        Integer,
        ForeignKey("claim_validation_run.id"),
        nullable=False,
        index=True,
    )

    rule_id = Column(
        Integer,
        ForeignKey("validation_rule.id"),
        nullable=False,
        index=True,
    )

    rule_version_id = Column(
        Integer,
        ForeignKey("validation_rule_version.id"),
        nullable=False,
        index=True,
    )

    applicability_status = Column(
        String(30),
        nullable=False,
    )

    result_status = Column(
        String(30),
        nullable=False,
    )

    severity = Column(
        String(30),
        nullable=False,
    )

    result_message = Column(
        Text,
        nullable=True,
    )

    evidence = Column(
        JSON,
        nullable=True,
    )

    review_required = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    evaluated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    validation_run = relationship(
        "ClaimValidationRun",
        back_populates="results",
    )

    rule = relationship("ValidationRule")
    rule_version = relationship("ValidationRuleVersion")