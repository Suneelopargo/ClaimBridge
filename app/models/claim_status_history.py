from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.models.base import Base


class ClaimStatusHistory(Base):
    __tablename__ = "claim_status_history"

    id = Column(Integer, primary_key=True, index=True)

    claim_summary_id = Column(
        Integer,
        ForeignKey("claim_summary.id"),
        nullable=False,
        index=True,
    )

    portal_connection_id = Column(
        Integer,
        ForeignKey("portal_connection.id"),
        nullable=False,
        index=True,
    )

    portal_claim_number = Column(String(100), nullable=False, index=True)

    payer = Column(String(100), nullable=True)

    status = Column(String(100), nullable=True, index=True)

    claimed_amount = Column(Numeric(12, 2), nullable=True)

    approved_amount = Column(Numeric(12, 2), nullable=True)

    date_of_admission = Column(Date, nullable=True)

    date_of_discharge = Column(Date, nullable=True)

    change_hash = Column(String(64), nullable=False, index=True)

    observed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    claim_summary = relationship("ClaimSummary", back_populates="status_history")