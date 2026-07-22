from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.models.base import Base


class ValidationRuleVersion(Base):
    __tablename__ = "validation_rule_version"

    __table_args__ = (
        UniqueConstraint(
            "rule_id",
            "version_number",
            name="uq_validation_rule_version",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    rule_id = Column(
        Integer,
        ForeignKey("validation_rule.id"),
        nullable=False,
        index=True,
    )

    version_number = Column(
        Integer,
        nullable=False,
    )

    applicability_expression = Column(
        JSON,
        nullable=True,
    )

    validation_expression = Column(
        JSON,
        nullable=False,
    )

    success_message = Column(
        Text,
        nullable=True,
    )

    failure_message = Column(
        Text,
        nullable=True,
    )

    effective_from = Column(
        Date,
        nullable=False,
    )

    effective_to = Column(
        Date,
        nullable=True,
    )

    is_published = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    change_reason = Column(
        Text,
        nullable=True,
    )

    created_by = Column(
        String(100),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    rule = relationship(
        "ValidationRule",
        back_populates="versions",
    )