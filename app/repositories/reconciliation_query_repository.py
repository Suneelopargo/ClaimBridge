from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.reconciliation_manual_details import ReconciliationManualDetails
from app.models.reconciliation_summary import ReconciliationSummary


class ReconciliationQueryRepository:
    def __init__(self, db: Session):
        self.db = db

    def search(
        self,
        page: int,
        page_size: int,
        search: str = None,
        claim_status: str = None,
        insurer: str = None,
        tpa: str = None,
        hospital_name: str = None,
    ):
        query = (
            self.db.query(ReconciliationSummary)
            .options(joinedload(ReconciliationSummary.manual_details))
        )

        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    ReconciliationSummary.patient_name.ilike(pattern),
                    ReconciliationSummary.claim_number.ilike(pattern),
                    ReconciliationSummary.ihx_ref_id.ilike(pattern),
                    ReconciliationSummary.uhid.ilike(pattern),
                    ReconciliationSummary.invoice_number.ilike(pattern),
                )
            )

        if claim_status:
            query = query.filter(
                ReconciliationSummary.claim_status == claim_status
            )

        if insurer:
            query = query.filter(
                ReconciliationSummary.insurance_company_name.ilike(
                    f"%{insurer.strip()}%"
                )
            )

        if tpa:
            query = query.filter(
                ReconciliationSummary.tpa_name.ilike(
                    f"%{tpa.strip()}%"
                )
            )

        if hospital_name:
            query = query.filter(
                ReconciliationSummary.hospital_name.ilike(
                    f"%{hospital_name.strip()}%"
                )
            )

        total = query.count()

        records = (
            query.order_by(ReconciliationSummary.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return records, total

    def find_by_id(self, record_id: int):
        return (
            self.db.query(ReconciliationSummary)
            .options(joinedload(ReconciliationSummary.manual_details))
            .filter(ReconciliationSummary.id == record_id)
            .first()
        )

    def get_or_create_manual_details(
        self,
        record: ReconciliationSummary,
    ) -> ReconciliationManualDetails:
        if record.manual_details:
            return record.manual_details

        manual = ReconciliationManualDetails(
            reconciliation_summary_id=record.id
        )
        self.db.add(manual)
        self.db.flush()
        return manual

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()
