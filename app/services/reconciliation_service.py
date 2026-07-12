from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import List

from sqlalchemy.orm import Session

from app.parsers.reconciliation_excel_parser import (
    ReconciliationExcelParser,
    ReconciliationParserError,
)
from app.repositories.reconciliation_repository import (
    ReconciliationRepository,
)


logger = logging.getLogger(__name__)


class ReconciliationImportError(Exception):
    """Raised when the reconciliation import cannot be completed."""


@dataclass(frozen=True)
class ReconciliationImportResult:
    batch_id: int
    file_name: str
    total_rows: int
    inserted: int
    updated: int
    unchanged: int
    failed: int
    skipped_blank_rows: int
    duration_seconds: float
    row_errors: List[dict]

    def to_dict(self) -> dict:
        return {
            "success": True,
            "batchId": self.batch_id,
            "fileName": self.file_name,
            "totalRows": self.total_rows,
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "failed": self.failed,
            "skippedBlankRows": self.skipped_blank_rows,
            "durationSeconds": self.duration_seconds,
            "rowErrors": self.row_errors,
        }


class ReconciliationService:
    def __init__(
        self,
        db: Session,
        parser: ReconciliationExcelParser | None = None,
    ):
        self.db = db
        self.parser = parser or ReconciliationExcelParser()
        self.repository = ReconciliationRepository(db)

    def import_latest_download(
        self,
        portal_connection_id: int,
        download_directory: str | Path,
    ) -> ReconciliationImportResult:
        latest_file = self.find_latest_download(download_directory)

        return self.import_file(
            portal_connection_id=portal_connection_id,
            file_path=latest_file,
        )

    def import_file(
        self,
        portal_connection_id: int,
        file_path: str | Path,
    ) -> ReconciliationImportResult:
        path = Path(file_path)
        started = perf_counter()
        batch = None

        try:
            batch = self.repository.create_import_batch(
                source_file_name=path.name,
                source_file_path=str(path),
            )

            parse_result = self.parser.parse(path)
            observed_at = datetime.utcnow()

            parsed_rows = parse_result.parsed_rows
            ihx_ref_ids = [
                parsed_row.ihx_ref_id
                for parsed_row in parsed_rows
            ]

            existing_map = (
                self.repository.find_existing_by_ihx_ref_ids(
                    portal_connection_id=portal_connection_id,
                    ihx_ref_ids=ihx_ref_ids,
                )
            )

            inserted = 0
            updated = 0
            unchanged = 0

            for parsed_row in parsed_rows:
                existing = existing_map.get(parsed_row.ihx_ref_id)

                if existing is None:
                    new_record = self.repository.add_new_record(
                        portal_connection_id=portal_connection_id,
                        batch_id=batch.id,
                        source_file_name=parse_result.source_file_name,
                        source_row_number=parsed_row.source_row_number,
                        values=parsed_row.values,
                        change_hash=parsed_row.change_hash,
                        observed_at=observed_at,
                    )
                    existing_map[parsed_row.ihx_ref_id] = new_record
                    inserted += 1
                    continue

                if existing.current_change_hash != parsed_row.change_hash:
                    self.repository.update_existing_record(
                        record=existing,
                        batch_id=batch.id,
                        source_file_name=parse_result.source_file_name,
                        source_row_number=parsed_row.source_row_number,
                        values=parsed_row.values,
                        change_hash=parsed_row.change_hash,
                        observed_at=observed_at,
                    )
                    updated += 1
                else:
                    self.repository.mark_unchanged_seen(
                        record=existing,
                        batch_id=batch.id,
                        source_file_name=parse_result.source_file_name,
                        source_row_number=parsed_row.source_row_number,
                        observed_at=observed_at,
                    )
                    unchanged += 1

            duration = round(perf_counter() - started, 3)

            row_errors = [
                {
                    "rowNumber": error.source_row_number,
                    "message": error.message,
                }
                for error in parse_result.row_errors[:100]
            ]

            self.repository.complete_import_batch(
                batch,
                total_rows=parse_result.total_excel_rows,
                inserted_rows=inserted,
                updated_rows=updated,
                unchanged_rows=unchanged,
                failed_rows=parse_result.failed_rows,
                duration_seconds=duration,
            )
            self.repository.commit()

            logger.info(
                "[ReconciliationImport] batch=%s file=%s total=%s "
                "inserted=%s updated=%s unchanged=%s failed=%s duration=%ss",
                batch.id,
                path.name,
                parse_result.total_excel_rows,
                inserted,
                updated,
                unchanged,
                parse_result.failed_rows,
                duration,
            )

            return ReconciliationImportResult(
                batch_id=batch.id,
                file_name=path.name,
                total_rows=parse_result.total_excel_rows,
                inserted=inserted,
                updated=updated,
                unchanged=unchanged,
                failed=parse_result.failed_rows,
                skipped_blank_rows=parse_result.skipped_blank_rows,
                duration_seconds=duration,
                row_errors=row_errors,
            )

        except Exception as exc:
            duration = round(perf_counter() - started, 3)

            self.repository.rollback()

            # Record a failed batch in a fresh transaction because rollback
            # removes the original uncommitted batch.
            try:
                failed_batch = self.repository.create_import_batch(
                    source_file_name=path.name,
                    source_file_path=str(path),
                )
                self.repository.fail_import_batch(
                    failed_batch,
                    error_message=str(exc) or repr(exc),
                    duration_seconds=duration,
                )
                self.repository.commit()
            except Exception:
                self.repository.rollback()
                logger.exception(
                    "[ReconciliationImport] Failed to persist failed batch"
                )

            logger.exception(
                "[ReconciliationImport] Import failed for file: %s",
                path,
            )

            if isinstance(exc, ReconciliationParserError):
                raise ReconciliationImportError(str(exc)) from exc

            raise ReconciliationImportError(
                f"Reconciliation import failed for {path.name}: "
                f"{str(exc) or repr(exc)}"
            ) from exc

    @staticmethod
    def find_latest_download(
        download_directory: str | Path,
    ) -> Path:
        directory = Path(download_directory)

        if not directory.exists():
            raise ReconciliationImportError(
                f"Reconciliation download directory does not exist: "
                f"{directory}"
            )

        candidates = [
            path
            for path in directory.iterdir()
            if path.is_file()
            and path.suffix.lower() in {".xlsx", ".xlsm"}
            and not path.name.startswith("~$")
        ]

        if not candidates:
            raise ReconciliationImportError(
                f"No reconciliation workbook found in: {directory}"
            )

        return max(
            candidates,
            key=lambda path: path.stat().st_mtime,
        )
