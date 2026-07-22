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
from app.models.activity_log import ActivityLog
from app.models.user import User
from app.models.validation_rule import ValidationRule
from app.models.validation_rule_version import ValidationRuleVersion
from app.models.validation_rule_document_type import (
    ValidationRuleDocumentType,
)
from app.models.claim_validation_run import ClaimValidationRun
from app.models.claim_validation_result import ClaimValidationResult


def main():
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully")


if __name__ == "__main__":
    main()