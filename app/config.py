import os

from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "India Claims Automation")
DATABASE_URL = os.getenv("DATABASE_URL")

IHX_USERNAME = os.getenv("IHX_USERNAME")
IHX_PASSWORD = os.getenv("IHX_PASSWORD")

IHX_PORTAL_CONNECTION_ID = int(
    os.getenv("IHX_PORTAL_CONNECTION_ID", "1")
)

IHX_HOSPITAL_NAME = os.getenv(
    "IHX_HOSPITAL_NAME",
    "HCG Demo Hospital",
)

IHX_RECONCILIATION_REPORT_URL = os.getenv(
    "IHX_RECONCILIATION_REPORT_URL",
    "",
).strip()

IHX_RECONCILIATION_DOWNLOAD_DIR = os.getenv(
    "IHX_RECONCILIATION_DOWNLOAD_DIR",
    str(Path("data") / "reconciliation" / "downloads"),
)

IHX_RECONCILIATION_EXPORT_TIMEOUT_MS = int(
    os.getenv("IHX_RECONCILIATION_EXPORT_TIMEOUT_MS", "120000")
)