from fastapi import APIRouter
from sqlalchemy import func

from app.database import SessionLocal
from app.models.claim_summary import ClaimSummary

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/claim-status-summary")
def claim_status_summary():
    db = SessionLocal()

    try:
        rows = (
            db.query(
                ClaimSummary.status,
                func.count(ClaimSummary.id).label("count"),
                func.coalesce(func.sum(ClaimSummary.claimed_amount), 0).label("claimed_amount"),
                func.coalesce(func.sum(ClaimSummary.approved_amount), 0).label("approved_amount"),
            )
            .group_by(ClaimSummary.status)
            .order_by(func.count(ClaimSummary.id).desc())
            .all()
        )

        return {
            "success": True,
            "totalClaims": sum(row.count for row in rows),
            "statuses": [
                {
                    "status": row.status or "Unknown",
                    "count": row.count,
                    "claimedAmount": float(row.claimed_amount),
                    "approvedAmount": float(row.approved_amount),
                }
                for row in rows
            ],
        }

    finally:
        db.close()