from sqlalchemy import func
from sqlalchemy.orm import joinedload
from app.models.reconciliation_summary import ReconciliationSummary
from app.models.reconciliation_manual_details import ReconciliationManualDetails
from app.services.reconciliation_record_service import ReconciliationRecordService
from app.services.reconciliation_filter_catalog import BY_FIELD

class ReconciliationFilterError(Exception):
    pass

class ReconciliationStructuredQueryService:
    EXPRESSIONS = {
        "claimStatus": ReconciliationSummary.claim_status,
        "insuranceCompany": ReconciliationSummary.insurance_company_name,
        "payorCompanyName": ReconciliationSummary.tpa_name,
        "hospitalName": ReconciliationSummary.hospital_name,
        "patientName": ReconciliationSummary.patient_name,
        "claimAuthNumber": ReconciliationSummary.claim_number,
        "uhid": ReconciliationSummary.uhid,
        "billNumber": ReconciliationSummary.invoice_number,
        "admittedDate": ReconciliationSummary.date_of_admission,
        "dischargedDate": ReconciliationSummary.date_of_discharge,
        "submissionDate": ReconciliationSummary.document_submission_date,
        "billAmount": ReconciliationSummary.claimed_amount,
        "payorAmount": ReconciliationSummary.approved_amount,
        "amountReceived": ReconciliationSummary.settled_amount,
        "amountReceivable": func.coalesce(
            ReconciliationManualDetails.amount_receivable_override,
            func.coalesce(ReconciliationSummary.approved_amount, 0)
            - func.coalesce(ReconciliationSummary.settled_amount, 0)
            - func.coalesce(ReconciliationSummary.tds_amount, 0),
        ),
        "financeRemarks": ReconciliationManualDetails.finance_remarks,
    }

    def __init__(self, db):
        self.db = db
        self.projector = ReconciliationRecordService(db)

    def search(self, request):
        query = (
            self.db.query(ReconciliationSummary)
            .outerjoin(
                ReconciliationManualDetails,
                ReconciliationManualDetails.reconciliation_summary_id == ReconciliationSummary.id,
            )
            .options(joinedload(ReconciliationSummary.manual_details))
        )

        for condition in request.filters:
            definition = BY_FIELD.get(condition.field)
            if not definition:
                raise ReconciliationFilterError(f"Unsupported filter field: {condition.field}")
            if condition.operator not in definition["operators"]:
                raise ReconciliationFilterError(
                    f"Operator '{condition.operator}' is not supported for '{condition.field}'"
                )
            expression = self.EXPRESSIONS[condition.field]
            query = query.filter(self._clause(expression, condition.operator, condition.value))

        total = query.count()

        for item in request.sort:
            expression = self.EXPRESSIONS.get(item.get("field"))
            if expression is not None:
                query = query.order_by(
                    expression.desc() if item.get("direction") == "desc" else expression.asc()
                )

        if not request.sort:
            query = query.order_by(ReconciliationSummary.id.desc())

        rows = (
            query.offset((request.page - 1) * request.page_size)
            .limit(request.page_size)
            .all()
        )

        return {
            "items": [self.projector._to_customer_record(row) for row in rows],
            "page": request.page,
            "pageSize": request.page_size,
            "totalRecords": total,
            "totalPages": (total + request.page_size - 1) // request.page_size if total else 0,
        }

    @staticmethod
    def _clause(expression, operator, value):
        if operator == "eq":
            return expression == value
        if operator == "in":
            if not isinstance(value, list):
                raise ReconciliationFilterError("'in' requires a list value")
            return expression.in_(value)
        if operator == "contains":
            return expression.ilike(f"%{value}%")
        if operator == "startsWith":
            return expression.ilike(f"{value}%")
        if operator == "gte":
            return expression >= value
        if operator == "lte":
            return expression <= value
        if operator == "between":
            if not isinstance(value, list) or len(value) != 2:
                raise ReconciliationFilterError("'between' requires two values")
            return expression.between(value[0], value[1])
        if operator == "isNull":
            return expression.is_(None)
        if operator == "isNotNull":
            return expression.isnot(None)
        raise ReconciliationFilterError(f"Unsupported operator: {operator}")
