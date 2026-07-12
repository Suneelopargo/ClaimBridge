from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.models.base import Base


class ReconciliationSummary(Base):
    """
    Current reconciliation snapshot for an IHX claim.

    All 43 fields exported by the IHX Power BI reconciliation report are
    preserved. The comments only group columns logically for maintainability;
    they do not change the physical database structure.
    """

    __tablename__ = "reconciliation_summary"

    __table_args__ = (
        UniqueConstraint(
            "portal_connection_id",
            "ihx_ref_id",
            name="uq_reconciliation_connection_ihx_ref_id",
        ),
    )

    # ------------------------------------------------------------------
    # Internal identity and source
    # ------------------------------------------------------------------

    id = Column(Integer, primary_key=True, index=True)

    portal_connection_id = Column(
        Integer,
        ForeignKey("portal_connection.id"),
        nullable=False,
        index=True,
    )

    last_import_batch_id = Column(
        Integer,
        ForeignKey("reconciliation_import_batch.id"),
        nullable=True,
        index=True,
    )

    source_file_name = Column(String(255), nullable=True)
    source_row_number = Column(Integer, nullable=True)

    # ------------------------------------------------------------------
    # IHX identity and hospital
    # ------------------------------------------------------------------

    ihx_ref_id = Column(String(100), nullable=False, index=True)
    hospital_name = Column(String(255), nullable=True, index=True)
    rohini_id = Column(String(100), nullable=True)

    # ------------------------------------------------------------------
    # Patient and member
    # ------------------------------------------------------------------

    patient_name = Column(String(255), nullable=True, index=True)
    patient_contact = Column(String(50), nullable=True)
    in_patient_number = Column(String(100), nullable=True, index=True)
    member_customer_id = Column(String(150), nullable=True)

    # ------------------------------------------------------------------
    # Admission
    # ------------------------------------------------------------------

    date_of_admission = Column(Date, nullable=True, index=True)
    date_of_discharge = Column(Date, nullable=True, index=True)

    # ------------------------------------------------------------------
    # Payer and policy
    # ------------------------------------------------------------------

    tpa_name = Column(String(255), nullable=True, index=True)
    insurance_company_name = Column(String(255), nullable=True, index=True)
    policy_number = Column(String(150), nullable=True)
    policy_type = Column(String(100), nullable=True)
    policy_holder_name = Column(String(255), nullable=True)
    employee_code = Column(String(150), nullable=True)

    # ------------------------------------------------------------------
    # Claim identity and lifecycle
    # ------------------------------------------------------------------

    claim_number = Column(String(150), nullable=True, index=True)
    initial_claim_number = Column(String(150), nullable=True)
    claim_creation_date = Column(Date, nullable=True)
    claim_status = Column(String(150), nullable=True, index=True)
    document_submission_date = Column(Date, nullable=True)
    payment_update_date = Column(Date, nullable=True)

    # ------------------------------------------------------------------
    # Financial values
    # ------------------------------------------------------------------

    claimed_amount = Column(Numeric(14, 2), nullable=True)
    approved_amount = Column(Numeric(14, 2), nullable=True)
    copay = Column(Numeric(14, 2), nullable=True)
    shortfall_amount = Column(Numeric(14, 2), nullable=True)
    hospital_discount = Column(Numeric(14, 2), nullable=True)
    patient_paid_amount = Column(Numeric(14, 2), nullable=True)
    settled_amount = Column(Numeric(14, 2), nullable=True)
    tds_amount = Column(Numeric(14, 2), nullable=True)

    # ------------------------------------------------------------------
    # Payment reference
    # ------------------------------------------------------------------

    cheque_neft_utr_number = Column(String(200), nullable=True, index=True)
    cheque_neft_utr_date = Column(Date, nullable=True)
    receipt_number = Column(String(150), nullable=True)

    # ------------------------------------------------------------------
    # Clinical and insurer information
    # ------------------------------------------------------------------

    treatment = Column(Text, nullable=True)
    diagnosis = Column(Text, nullable=True)
    insurer_comments = Column(Text, nullable=True)

    # ------------------------------------------------------------------
    # Hospital billing identifiers
    # ------------------------------------------------------------------

    uhid = Column(String(150), nullable=True, index=True)
    invoice_number = Column(String(150), nullable=True, index=True)

    # ------------------------------------------------------------------
    # Courier and dispatch
    # ------------------------------------------------------------------

    courier_agency = Column(String(255), nullable=True)
    courier_destination = Column(String(255), nullable=True)
    courier_dispatch_date = Column(Date, nullable=True)
    courier_name = Column(String(255), nullable=True)
    courier_provider = Column(String(255), nullable=True)
    courier_track_id = Column(String(255), nullable=True, index=True)

    # ------------------------------------------------------------------
    # Synchronization and audit
    # ------------------------------------------------------------------

    current_change_hash = Column(String(64), nullable=True, index=True)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    portal_connection = relationship("PortalConnection")

    last_import_batch = relationship(
        "ReconciliationImportBatch",
        back_populates="reconciliation_records",
    )

    manual_details = relationship(
        "ReconciliationManualDetails",
        back_populates="reconciliation_summary",
        uselist=False,
        cascade="all, delete-orphan",
    )