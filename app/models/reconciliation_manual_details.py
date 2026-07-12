from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.models.base import Base


class ReconciliationManualDetails(Base):
    __tablename__ = "reconciliation_manual_details"

    id = Column(Integer, primary_key=True, index=True)

    reconciliation_summary_id = Column(
        Integer,
        ForeignKey("reconciliation_summary.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Optional customer fields not reliably available from IHX
    bill_date = Column(Date, nullable=True)
    received_date = Column(Date, nullable=True)
    mode_of_dispatch = Column(String(100), nullable=True)
    waybill_pod_by_hand = Column(String(255), nullable=True)

    query_date = Column(Date, nullable=True)
    query_raised = Column(Text, nullable=True)
    query_raised_date = Column(Date, nullable=True)
    query_revert_date = Column(Date, nullable=True)

    total_discount_amount = Column(Numeric(14, 2), nullable=True)
    payor_discount = Column(Numeric(14, 2), nullable=True)
    patient_discount = Column(Numeric(14, 2), nullable=True)

    # Optional overrides. APIs derive these when override is null.
    payor_net_amount_override = Column(Numeric(14, 2), nullable=True)
    patient_net_amount_override = Column(Numeric(14, 2), nullable=True)
    amount_receivable_override = Column(Numeric(14, 2), nullable=True)

    disallowance_amount = Column(Numeric(14, 2), nullable=True)
    remarks_reason = Column(Text, nullable=True)
    disallow_contestable = Column(Boolean, nullable=True)

    disallowance_bed_charges = Column(Numeric(14, 2), nullable=True)
    disallowance_consumables = Column(Numeric(14, 2), nullable=True)
    disallowance_investigation = Column(Numeric(14, 2), nullable=True)
    disallowance_professional_fees = Column(Numeric(14, 2), nullable=True)
    disallowance_equipment = Column(Numeric(14, 2), nullable=True)
    disallowance_wrong_billing = Column(Numeric(14, 2), nullable=True)
    disallowance_wrong_tariff = Column(Numeric(14, 2), nullable=True)
    disallowance_miscellaneous = Column(Numeric(14, 2), nullable=True)

    status_of_disallowance = Column(String(150), nullable=True)
    escalation_raised = Column(Text, nullable=True)

    accounts_submission_date = Column(Date, nullable=True)
    finance_received_date = Column(Date, nullable=True)
    sap_settled_date = Column(Date, nullable=True)
    finance_remarks = Column(Text, nullable=True)

    created_by = Column(String(150), nullable=True)
    updated_by = Column(String(150), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    reconciliation_summary = relationship(
        "ReconciliationSummary",
        back_populates="manual_details",
    )
