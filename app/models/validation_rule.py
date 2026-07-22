from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.models.base import Base


class ValidationRule(Base):
    __tablename__ = "validation_rule"

    id = Column(Integer, primary_key=True, index=True)

    rule_code = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    rule_name = Column(
        String(200),
        nullable=False,
    )

    description = Column(
        Text,
        nullable=True,
    )

    category = Column(
        String(50),
        nullable=False,
        index=True,
    )

    rule_type = Column(
        String(50),
        nullable=False,
        index=True,
    )

    payer_code = Column(
        String(50),
        nullable=True,
        index=True,
    )

    severity = Column(
        String(30),
        nullable=False,
        default="WARNING",
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
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

    updated_by = Column(
        String(100),
        nullable=True,
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    versions = relationship(
        "ValidationRuleVersion",
        back_populates="rule",
        cascade="all, delete-orphan",
    )

    document_types = relationship(
        "ValidationRuleDocumentType",
        back_populates="rule",
        cascade="all, delete-orphan",
    )