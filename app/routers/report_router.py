from fastapi import APIRouter
from fastapi.responses import FileResponse
from app.database import SessionLocal
from app.reports.claim_excel_report import ClaimExcelReport

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.get("/claims/excel")
def download_claim_summary_excel():
    db = SessionLocal()

    try:
        file_path = ClaimExcelReport.generate_claim_summary_excel(db)

        return FileResponse(
            path=file_path,
            filename=file_path.split("/")[-1],
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    finally:
        db.close()