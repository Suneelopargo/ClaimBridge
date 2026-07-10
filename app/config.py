import os

from dotenv import load_dotenv

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