from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.models.base import Base


class ValidationRuleDocumentType(Base):
    __tablename__ = "validation_rule_document_type"

    __table_args__ = (
        UniqueConstraint(
            "rule_id",
            "document_type",
            "document_role",
            name="uq_rule_document_type_role",
        ),
    )

    id = Column(Integer, primary_key=True)

    rule_id = Column(
        Integer,
        ForeignKey("validation_rule.id"),
        nullable=False,
        index=True,
    )

    document_type = Column(
        String(100),
        nullable=False,
        index=True,
    )

    document_role = Column(
        String(30),
        nullable=False,
        default="EVIDENCE",
    )

    is_mandatory = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    rule = relationship(
        "ValidationRule",
        back_populates="document_types",
    )