from app.database import engine
from app.models.base import Base

# Import models so SQLAlchemy knows them
from app.models.portal import Portal
from app.models.portal_connection import PortalConnection
from app.models.claim_summary import ClaimSummary
from app.models.claim_status_history import ClaimStatusHistory
from app.models.reconciliation_import_batch import ReconciliationImportBatch
from app.models.reconciliation_summary import ReconciliationSummary
from app.models.reconciliation_manual_details import (
    ReconciliationManualDetails,
)
from app.models.user import User


def main():
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully")


if __name__ == "__main__":
    main()