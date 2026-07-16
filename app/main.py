from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.logging_config as logging_config
from app.config import APP_NAME, CORS_ALLOWED_ORIGINS
from app.database import test_db_connection
from app.routers.claim_dashboard_router import router as dashboard_router
from app.routers.ihx_router import router as ihx_router
from app.routers.reconciliation_router import router as reconciliation_router
from app.routers.report_router import router as report_router
from app.routers.reconciliation_query_router import (
    router as reconciliation_query_router,
)
from app.routers.reconciliation_report_router import router as reconciliation_report_router
from app.routers.reconciliation_filter_router import (
    router as reconciliation_filter_router,
)
from app.routers.auth_router import router as auth_router
from app.routers.claim_packet_router import (
    router as claim_packet_router,
)


app = FastAPI(
    title=APP_NAME,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(ihx_router)
app.include_router(report_router)
app.include_router(dashboard_router)
app.include_router(reconciliation_router)
app.include_router(reconciliation_query_router)
app.include_router(reconciliation_report_router)
app.include_router(reconciliation_filter_router)
app.include_router(auth_router)
app.include_router(claim_packet_router)


@app.get("/")
def root():
    return {
        "message": f"{APP_NAME} API running",
    }


@app.get("/health/db")
def health_db():
    test_db_connection()

    return {
        "success": True,
        "database": "connected",
    }