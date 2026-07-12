from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.reconciliation_summary import ReconciliationSummary
from app.schemas.reconciliation_filter_schemas import ReconciliationSearchRequest
from app.services.reconciliation_filter_catalog import FILTERS
from app.services.reconciliation_structured_query_service import (
    ReconciliationFilterError,
    ReconciliationStructuredQueryService,
)

router = APIRouter(prefix="/api/reconciliation", tags=["Reconciliation Filters"])

DISTINCT_COLUMNS = {
    "claimStatus": ReconciliationSummary.claim_status,
    "insuranceCompany": ReconciliationSummary.insurance_company_name,
    "payorCompanyName": ReconciliationSummary.tpa_name,
    "hospitalName": ReconciliationSummary.hospital_name,
}


@router.get("/filter-options")
def get_filter_options(db: Session = Depends(get_db)):
    response = []
    for definition in FILTERS:
        item = dict(definition)
        column = DISTINCT_COLUMNS.get(item["field"])
        if column is not None:
            rows = (
                db.query(column)
                .filter(column.isnot(None))
                .filter(func.trim(column) != "")
                .distinct()
                .order_by(column.asc())
                .all()
            )
            item["values"] = [row[0] for row in rows]
        response.append(item)
    return {"filters": response, "totalFilters": len(response)}

@router.post("/records/search")
def search_records(request: ReconciliationSearchRequest, db: Session = Depends(get_db)):
    try:
        return ReconciliationStructuredQueryService(db).search(request)
    except ReconciliationFilterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
