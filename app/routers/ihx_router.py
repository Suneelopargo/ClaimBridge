from fastapi import APIRouter
from app.connectors.ihx.ihx_connector import IHXConnector
from app.database import SessionLocal
from app.repositories.claim_summary_repository import ClaimSummaryRepository
from app.services.claim_summary_service import ClaimSummaryService
import logging
import traceback
from app.config import (
    IHX_HOSPITAL_NAME,
    IHX_PASSWORD,
    IHX_PORTAL_CONNECTION_ID,
    IHX_USERNAME,
)

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/ihx", tags=["IHX"])
logger = logging.getLogger(__name__)


@router.post("/sync")
def sync_ihx_claims(
    start_page: int = 1,
    max_pages: int | None = 25,
):
    db = SessionLocal()
    stage = "initialization"

    try:
        stage = "creating connector"

        with IHXConnector(
                username=IHX_USERNAME,
                password=IHX_PASSWORD,
                headless=False,
                slow_mo=300,
        ) as connector:

            stage = "IHX login and OTP"
            connector.login_with_graph_otp()

            stage = "opening claim tracking"
            connector.open_claim_tracking()

            stage = "extracting claim pages"
            raw_claims = connector.extract_all_claim_pages(
                start_page=start_page,
                max_pages=max_pages,
            )

            stage = "normalizing claims"
            normalized_claims = ClaimSummaryService.normalize_claims(raw_claims)

            stage = "saving claims"
            repository = ClaimSummaryRepository(db)

            synced_claims = repository.synchronize_claims(
                portal_connection_id=IHX_PORTAL_CONNECTION_ID,
                hospital_name=IHX_HOSPITAL_NAME,
                claims=normalized_claims,
            )

            return {
                "success": True,
                "startPage": start_page,
                "pagesRequested": max_pages,
                "rawClaimsExtracted": len(raw_claims),
                "claimsSynced": len(synced_claims),
            }

    except Exception as exc:
        db.rollback()
        logger.exception("IHX sync failed at stage: %s", stage)

        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "stage": stage,
                "errorType": type(exc).__name__,
                "error": str(exc) or repr(exc),
            },
        )

    finally:
        db.close()
