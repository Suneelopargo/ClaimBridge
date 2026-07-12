import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.reconciliation_schemas import (
    ReconciliationManualFieldsUpdate,
)
from app.services.reconciliation_record_service import (
    ReconciliationRecordService,
)


router = APIRouter(
    prefix="/api/reconciliation",
    tags=["Reconciliation"],
)

logger = logging.getLogger(__name__)


@router.get("/report-fields")
def get_reconciliation_report_fields(
    db: Session = Depends(get_db),
):
    service = ReconciliationRecordService(db)
    fields = service.get_report_fields()
    return {
        "fields": fields,
        "totalFields": len(fields),
        "defaultFields": [f["field"] for f in fields if f.get("defaultVisible")],
        "exportableFields": [f["field"] for f in fields if f.get("exportable")],
    }


@router.get("/records")
def get_reconciliation_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    search: Optional[str] = None,
    claim_status: Optional[str] = None,
    insurer: Optional[str] = None,
    tpa: Optional[str] = None,
    hospital_name: Optional[str] = None,
    db: Session = Depends(get_db),
):
    service = ReconciliationRecordService(db)

    return service.get_records(
        page=page,
        page_size=page_size,
        search=search,
        claim_status=claim_status,
        insurer=insurer,
        tpa=tpa,
        hospital_name=hospital_name,
    )


@router.get("/records/{record_id}")
def get_reconciliation_record(
    record_id: int,
    db: Session = Depends(get_db),
):
    service = ReconciliationRecordService(db)
    record = service.get_record(record_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Reconciliation record not found",
        )

    return record


@router.patch("/records/{record_id}/manual-fields")
def update_reconciliation_manual_fields(
    record_id: int,
    payload: ReconciliationManualFieldsUpdate,
    db: Session = Depends(get_db),
):
    service = ReconciliationRecordService(db)

    try:
        record = service.update_manual_fields(
            record_id=record_id,
            payload=payload,
        )

        if record is None:
            raise HTTPException(
                status_code=404,
                detail="Reconciliation record not found",
            )

        return {
            "success": True,
            "record": record,
        }

    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception(
            "Unable to update manual reconciliation fields"
        )
        raise HTTPException(
            status_code=500,
            detail=str(exc) or "Manual field update failed",
        )
