from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from app.models.base import Base


class ClaimValidationRun(Base):
    __tablename__ = "claim_validation_run"

    id = Column(Integer, primary_key=True, index=True)

    claim_id = Column(
        String(100),
        nullable=False,
        index=True,
    )

    patient_name = Column(
        String(255),
        nullable=True,
    )

    payer_code = Column(
        String(50),
        nullable=True,
        index=True,
    )

    source_manifest_path = Column(
        String(1000),
        nullable=True,
    )

    status = Column(
        String(30),
        nullable=False,
        default="RUNNING",
    )

    readiness_score = Column(
        Float,
        nullable=True,
    )

    total_rules = Column(Integer, nullable=False, default=0)
    applicable_rules = Column(Integer, nullable=False, default=0)
    passed_rules = Column(Integer, nullable=False, default=0)
    failed_rules = Column(Integer, nullable=False, default=0)
    warning_rules = Column(Integer, nullable=False, default=0)
    not_applicable_rules = Column(Integer, nullable=False, default=0)
    manual_review_rules = Column(Integer, nullable=False, default=0)

    started_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    completed_at = Column(
        DateTime,
        nullable=True,
    )

    results = relationship(
        "ClaimValidationResult",
        back_populates="validation_run",
        cascade="all, delete-orphan",
    )