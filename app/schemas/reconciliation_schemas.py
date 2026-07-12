from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class ReconciliationManualFieldsUpdate(BaseModel):
    bill_date: Optional[date] = None
    received_date: Optional[date] = None
    mode_of_dispatch: Optional[str] = None
    waybill_pod_by_hand: Optional[str] = None

    query_date: Optional[date] = None
    query_raised: Optional[str] = None
    query_raised_date: Optional[date] = None
    query_revert_date: Optional[date] = None

    total_discount_amount: Optional[Decimal] = None
    payor_discount: Optional[Decimal] = None
    patient_discount: Optional[Decimal] = None

    payor_net_amount_override: Optional[Decimal] = None
    patient_net_amount_override: Optional[Decimal] = None
    amount_receivable_override: Optional[Decimal] = None

    disallowance_amount: Optional[Decimal] = None
    remarks_reason: Optional[str] = None
    disallow_contestable: Optional[bool] = None

    disallowance_bed_charges: Optional[Decimal] = None
    disallowance_consumables: Optional[Decimal] = None
    disallowance_investigation: Optional[Decimal] = None
    disallowance_professional_fees: Optional[Decimal] = None
    disallowance_equipment: Optional[Decimal] = None
    disallowance_wrong_billing: Optional[Decimal] = None
    disallowance_wrong_tariff: Optional[Decimal] = None
    disallowance_miscellaneous: Optional[Decimal] = None

    status_of_disallowance: Optional[str] = None
    escalation_raised: Optional[str] = None

    accounts_submission_date: Optional[date] = None
    finance_received_date: Optional[date] = None
    sap_settled_date: Optional[date] = None
    finance_remarks: Optional[str] = None

    updated_by: Optional[str] = None
