from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship
from sqlalchemy import UniqueConstraint

from app.models.base import Base


class ClaimSummary(Base):
    __tablename__ = "claim_summary"

    __table_args__ = (
        UniqueConstraint(
            "portal_connection_id",
            "portal_claim_number",
            name="uq_claim_summary_connection_claim_number",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    portal_connection_id = Column(
        Integer,
        ForeignKey("portal_connection.id"),
        nullable=False,
        index=True,
    )

    hospital_name = Column(String(150), nullable=False, index=True)

    payer = Column(String(100), nullable=True, index=True)

    portal_claim_number = Column(String(100), nullable=False, index=True)

    patient_name = Column(String(150), nullable=True)

    claimed_amount = Column(Numeric(12, 2), nullable=True)

    approved_amount = Column(Numeric(12, 2), nullable=True)

    status = Column(String(100), nullable=True, index=True)

    date_of_admission = Column(Date, nullable=True)

    date_of_discharge = Column(Date, nullable=True)

    current_change_hash = Column(String(64), nullable=True)

    last_synced_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    portal_connection = relationship(
        "PortalConnection",
        back_populates="claim_summaries",
    )

    status_history = relationship(
        "ClaimStatusHistory",
        back_populates="claim_summary",
        cascade="all, delete-orphan",
    )