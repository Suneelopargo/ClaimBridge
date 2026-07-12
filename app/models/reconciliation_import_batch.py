from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


class ReconciliationImportBatch(Base):
    __tablename__ = "reconciliation_import_batch"

    id = Column(Integer, primary_key=True, index=True)

    source_file_name = Column(String(255), nullable=False)
    source_file_path = Column(String(500), nullable=True)

    status = Column(String(30), nullable=False, default="STARTED", index=True)

    total_rows = Column(Integer, nullable=False, default=0)
    inserted_rows = Column(Integer, nullable=False, default=0)
    updated_rows = Column(Integer, nullable=False, default=0)
    unchanged_rows = Column(Integer, nullable=False, default=0)
    failed_rows = Column(Integer, nullable=False, default=0)

    error_message = Column(Text, nullable=True)
    duration_seconds = Column(Numeric(12, 3), nullable=True)

    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    reconciliation_records = relationship(
        "ReconciliationSummary",
        back_populates="last_import_batch",
    )
