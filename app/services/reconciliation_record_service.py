from decimal import Decimal
from math import ceil

from sqlalchemy.orm import Session

from app.repositories.reconciliation_query_repository import (
    ReconciliationQueryRepository,
)
from app.services.reconciliation_field_catalog import (
    CUSTOMER_RECONCILIATION_FIELDS,
)


def _decimal_or_zero(value):
    return value if value is not None else Decimal("0.00")


def _serialize(value):
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


class ReconciliationRecordService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = ReconciliationQueryRepository(db)

    @staticmethod
    def get_report_fields():
        return CUSTOMER_RECONCILIATION_FIELDS

    def get_records(
        self,
        page: int,
        page_size: int,
        search: str = None,
        claim_status: str = None,
        insurer: str = None,
        tpa: str = None,
        hospital_name: str = None,
    ):
        records, total = self.repository.search(
            page=page,
            page_size=page_size,
            search=search,
            claim_status=claim_status,
            insurer=insurer,
            tpa=tpa,
            hospital_name=hospital_name,
        )

        return {
            "items": [self._to_customer_record(r) for r in records],
            "page": page,
            "pageSize": page_size,
            "totalRecords": total,
            "totalPages": ceil(total / page_size) if total else 0,
        }

    def get_record(self, record_id: int):
        record = self.repository.find_by_id(record_id)
        if record is None:
            return None
        return self._to_customer_record(record)

    def update_manual_fields(self, record_id: int, payload):
        record = self.repository.find_by_id(record_id)
        if record is None:
            return None

        manual = self.repository.get_or_create_manual_details(record)

        values = payload.model_dump(exclude_unset=True)

        for field_name, value in values.items():
            setattr(manual, field_name, value)

        self.repository.commit()

        refreshed = self.repository.find_by_id(record_id)
        return self._to_customer_record(refreshed)

    @staticmethod
    def _to_customer_record(record):
        manual = record.manual_details

        claimed = _decimal_or_zero(record.claimed_amount)
        approved = _decimal_or_zero(record.approved_amount)
        patient_paid = _decimal_or_zero(record.patient_paid_amount)
        settled = _decimal_or_zero(record.settled_amount)
        tds = _decimal_or_zero(record.tds_amount)
        hospital_discount = _decimal_or_zero(record.hospital_discount)

        total_discount = (
            manual.total_discount_amount
            if manual and manual.total_discount_amount is not None
            else hospital_discount
        )

        payor_net = (
            manual.payor_net_amount_override
            if manual and manual.payor_net_amount_override is not None
            else approved - _decimal_or_zero(
                manual.payor_discount if manual else None
            )
        )

        patient_net = (
            manual.patient_net_amount_override
            if manual and manual.patient_net_amount_override is not None
            else patient_paid - _decimal_or_zero(
                manual.patient_discount if manual else None
            )
        )

        amount_receivable = (
            manual.amount_receivable_override
            if manual and manual.amount_receivable_override is not None
            else approved - settled - tds
        )

        data = {
            "id": record.id,
            "ihxRefId": record.ihx_ref_id,
            "uhid": record.uhid,
            "patientName": record.patient_name,
            "admissionNumber": record.in_patient_number,
            "admittedDate": record.date_of_admission,
            "dischargedDate": record.date_of_discharge,

            "insuranceCompany": record.insurance_company_name,
            "payorCompanyName": record.tpa_name,
            "policyNumber": record.policy_number,
            "claimAuthNumber": record.claim_number,

            "billNumber": record.invoice_number,
            "billDate": manual.bill_date if manual else None,
            "billAmount": claimed,
            "payorAmount": approved,
            "patientAmount": patient_paid,
            "copay": record.copay,
            "hospitalDiscount": record.hospital_discount,
            "totalDiscountAmount": total_discount,
            "payorDiscount": manual.payor_discount if manual else None,
            "patientDiscount": manual.patient_discount if manual else None,
            "payorNetAmount": payor_net,
            "patientNetAmount": patient_net,
            "amountReceived": settled,
            "tds": record.tds_amount,
            "amountReceivable": amount_receivable,

            "claimStatus": record.claim_status,
            "submissionDate": record.document_submission_date,
            "utrChequeNumber": record.cheque_neft_utr_number,
            "utrChequeDate": record.cheque_neft_utr_date,
            "receivedDate": manual.received_date if manual else None,
            "modeOfDispatch": manual.mode_of_dispatch if manual else None,
            "waybillPodByHand": (
                manual.waybill_pod_by_hand if manual else None
            ),

            "queryDate": manual.query_date if manual else None,
            "queryRaised": manual.query_raised if manual else None,
            "queryRaisedDate": (
                manual.query_raised_date if manual else None
            ),
            "queryRevertDate": (
                manual.query_revert_date if manual else None
            ),

            "disallowanceAmount": (
                manual.disallowance_amount if manual else None
            ),
            "remarksReason": manual.remarks_reason if manual else None,
            "disallowContestable": (
                manual.disallow_contestable if manual else None
            ),
            "statusOfDisallowance": (
                manual.status_of_disallowance if manual else None
            ),
            "escalationRaised": (
                manual.escalation_raised if manual else None
            ),
            "accountsSubmissionDate": (
                manual.accounts_submission_date if manual else None
            ),
            "financeReceivedDate": (
                manual.finance_received_date if manual else None
            ),
            "sapSettledDate": (
                manual.sap_settled_date if manual else None
            ),
            "financeRemarks": manual.finance_remarks if manual else None,

            "hospitalName": record.hospital_name,
            "lastSeenAt": record.last_seen_at,
            "updatedAt": record.updated_at,
        }

        return {key: _serialize(value) for key, value in data.items()}
