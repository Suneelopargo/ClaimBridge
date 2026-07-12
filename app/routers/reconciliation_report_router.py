import re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.reconciliation_report_schemas import ReconciliationReportExportRequest
from app.services.reconciliation_export_service import ReconciliationExportError, ReconciliationExportService

router = APIRouter(prefix="/api/reconciliation/reports", tags=["Reconciliation Reports"])

@router.post("/export")
def export_reconciliation_report(
    request: ReconciliationReportExportRequest,
    db: Session = Depends(get_db),
):
    service = ReconciliationExportService(db)
    try:
        output, record_count = service.export(request)
        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", request.report_name or "reconciliation_report").strip("_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_name or 'reconciliation_report'}_{timestamp}.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Record-Count": str(record_count),
            },
        )
    except ReconciliationExportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc) or "Report export failed") from exc
