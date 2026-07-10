from fastapi import FastAPI

from app.config import APP_NAME
from app.database import test_db_connection
from app.routers.ihx_router import router as ihx_router
from app.routers.report_router import router as report_router
from app.routers.claim_dashboard_router import router as dashboard_router

app = FastAPI(title=APP_NAME)


@app.get("/")
def root():
    return {"message": "India Claims Automation API running"}


@app.get("/health/db")
def health_db():
    test_db_connection()
    return {
        "success": True,
        "database": "connected",
    }


app.router.include_router(ihx_router)
app.router.include_router(report_router)
app.router.include_router(dashboard_router)