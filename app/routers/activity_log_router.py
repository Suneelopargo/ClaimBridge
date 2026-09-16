from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.activity_log import ActivityLog, ist_now
from app.schemas.activity_log_schemas import (
    ActivityLogCreateRequest,
    ActivityLogItem,
    ActivityLogListResponse,
)
from app.dependencies.auth_dependencies import (
    get_current_user,
    require_role,
)
from app.models.user import User

router = APIRouter(prefix="/api/activity-logs", tags=["Activity Logs"])


@router.post("", response_model=ActivityLogItem)
def create_activity_log(
    payload: ActivityLogCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    activity_log = ActivityLog(
        username=current_user.username,
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
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    current_user: User = Depends(
        require_role("SUPERUSER")
    ),
    db: Session = Depends(get_db),
):

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
