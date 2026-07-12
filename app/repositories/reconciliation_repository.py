from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List

from sqlalchemy.orm import Session

from app.models.reconciliation_import_batch import ReconciliationImportBatch
from app.models.reconciliation_summary import ReconciliationSummary


class ReconciliationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_import_batch(
        self,
        source_file_name: str,
        source_file_path: str | None = None,
    ) -> ReconciliationImportBatch:
        batch = ReconciliationImportBatch(
            source_file_name=source_file_name,
            source_file_path=source_file_path,
            status="STARTED",
            started_at=datetime.utcnow(),
        )
        self.db.add(batch)
        self.db.flush()
        return batch

    def find_existing_by_ihx_ref_ids(
        self,
        portal_connection_id: int,
        ihx_ref_ids: Iterable[str],
    ) -> Dict[str, ReconciliationSummary]:
        normalized_ids = list(dict.fromkeys(ihx_ref_ids))

        if not normalized_ids:
            return {}

        records = (
            self.db.query(ReconciliationSummary)
            .filter(
                ReconciliationSummary.portal_connection_id
                == portal_connection_id,
                ReconciliationSummary.ihx_ref_id.in_(normalized_ids),
            )
            .all()
        )

        return {
            record.ihx_ref_id: record
            for record in records
        }

    def add_new_record(
        self,
        portal_connection_id: int,
        batch_id: int,
        source_file_name: str,
        source_row_number: int,
        values: dict,
        change_hash: str,
        observed_at: datetime,
    ) -> ReconciliationSummary:
        record = ReconciliationSummary(
            portal_connection_id=portal_connection_id,
            last_import_batch_id=batch_id,
            source_file_name=source_file_name,
            source_row_number=source_row_number,
            current_change_hash=change_hash,
            last_seen_at=observed_at,
            **values,
        )
        self.db.add(record)
        return record

    @staticmethod
    def update_existing_record(
        record: ReconciliationSummary,
        batch_id: int,
        source_file_name: str,
        source_row_number: int,
        values: dict,
        change_hash: str,
        observed_at: datetime,
    ) -> None:
        # Only IHX-owned fields are present in `values`.
        # Manual/customer-entered fields are therefore preserved.
        for attribute_name, value in values.items():
            setattr(record, attribute_name, value)

        record.last_import_batch_id = batch_id
        record.source_file_name = source_file_name
        record.source_row_number = source_row_number
        record.current_change_hash = change_hash
        record.last_seen_at = observed_at
        record.updated_at = observed_at

    @staticmethod
    def mark_unchanged_seen(
        record: ReconciliationSummary,
        batch_id: int,
        source_file_name: str,
        source_row_number: int,
        observed_at: datetime,
    ) -> None:
        record.last_import_batch_id = batch_id
        record.source_file_name = source_file_name
        record.source_row_number = source_row_number
        record.last_seen_at = observed_at

    @staticmethod
    def complete_import_batch(
        batch: ReconciliationImportBatch,
        *,
        total_rows: int,
        inserted_rows: int,
        updated_rows: int,
        unchanged_rows: int,
        failed_rows: int,
        duration_seconds: float,
    ) -> None:
        batch.status = "COMPLETED"
        batch.total_rows = total_rows
        batch.inserted_rows = inserted_rows
        batch.updated_rows = updated_rows
        batch.unchanged_rows = unchanged_rows
        batch.failed_rows = failed_rows
        batch.duration_seconds = duration_seconds
        batch.completed_at = datetime.utcnow()

    @staticmethod
    def fail_import_batch(
        batch: ReconciliationImportBatch,
        error_message: str,
        duration_seconds: float,
    ) -> None:
        batch.status = "FAILED"
        batch.error_message = error_message[:10000]
        batch.duration_seconds = duration_seconds
        batch.completed_at = datetime.utcnow()

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
