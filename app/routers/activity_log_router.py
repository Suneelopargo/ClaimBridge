from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.activity_log import ActivityLog, ist_now
from app.schemas.activity_log_schemas import (
    ActivityLogCreateRequest,
    ActivityLogItem,
    ActivityLogListResponse,
)

router = APIRouter(prefix="/api/activity-logs", tags=["Activity Logs"])


@router.post("", response_model=ActivityLogItem)
def create_activity_log(
    payload: ActivityLogCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    activity_log = ActivityLog(
        username=payload.username,
        action_type=payload.action_type,
        target=payload.target,
        details=payload.details,
        ip_address=request.client.host if request.client else None,
        timestamp=ist_now(),
    )

    db.add(activity_log)
    db.commit()
    db.refresh(activity_log)

    return activity_log


@router.get("", response_model=ActivityLogListResponse)
def list_activity_logs(
    requester_role: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
):
    if requester_role.strip().lower() != "superuser":
        raise HTTPException(status_code=403, detail="Only superuser can access activity logs")

    base_query = db.query(ActivityLog)
    total = base_query.count()

    items = (
        base_query
        .order_by(ActivityLog.timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": items,
        "total": total,
    }
