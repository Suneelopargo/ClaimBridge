import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import (
    IHX_PASSWORD,
    IHX_PORTAL_CONNECTION_ID,
    IHX_RECONCILIATION_DOWNLOAD_DIR,
    IHX_USERNAME,
)
from app.connectors.ihx.reconciliation_connector import (
    IHXReconciliationConnector,
)
from app.database import get_db
from app.services.reconciliation_service import (
    ReconciliationImportError,
    ReconciliationService,
)


router = APIRouter(
    prefix="/api/reconciliation",
    tags=["Reconciliation"],
)

logger = logging.getLogger(__name__)


@router.post("/download")
def download_ihx_reconciliation_report():
    stage = "initialization"

    try:
        if not IHX_USERNAME or not IHX_PASSWORD:
            raise ValueError(
                "IHX_USERNAME and IHX_PASSWORD must be configured"
            )

        stage = "creating connector"

        with IHXReconciliationConnector(
            username=IHX_USERNAME,
            password=IHX_PASSWORD,
            headless=True,
            slow_mo=300,
        ) as connector:
            stage = "IHX login and OTP"
            connector.login_with_graph_otp()

            stage = "opening and downloading reconciliation report"
            downloaded_file = (
                connector.open_and_download_reconciliation_report()
            )

        file_path = Path(downloaded_file)

        return {
            "success": True,
            "fileName": file_path.name,
            "fileSizeBytes": file_path.stat().st_size,
            "message": "IHX reconciliation report downloaded successfully",
        }

    except Exception as exc:
        logger.exception(
            "IHX reconciliation download failed at stage: %s",
            stage,
        )

        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "stage": stage,
                "errorType": type(exc).__name__,
                "error": str(exc) or repr(exc),
            },
        ) from exc


@router.post("/import")
def import_latest_reconciliation_report(
    db: Session = Depends(get_db),
):
    """
    Imports the most recently downloaded IHX reconciliation workbook.

    Full workbook parsing is performed every time. New rows are inserted,
    changed rows are updated, unchanged rows are skipped, and missing rows are
    never deleted automatically.
    """
    stage = "locating latest reconciliation workbook"

    try:
        service = ReconciliationService(db)

        stage = "parsing and synchronizing reconciliation workbook"

        result = service.import_latest_download(
            portal_connection_id=IHX_PORTAL_CONNECTION_ID,
            download_directory=IHX_RECONCILIATION_DOWNLOAD_DIR,
        )

        return result.to_dict()

    except ReconciliationImportError as exc:
        logger.exception(
            "Reconciliation import failed at stage: %s",
            stage,
        )

        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "stage": stage,
                "errorType": type(exc).__name__,
                "error": str(exc),
            },
        ) from exc

    except Exception as exc:
        db.rollback()
        logger.exception(
            "Unexpected reconciliation import failure at stage: %s",
            stage,
        )

        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "stage": stage,
                "errorType": type(exc).__name__,
                "error": str(exc) or repr(exc),
            },
        ) from exc
