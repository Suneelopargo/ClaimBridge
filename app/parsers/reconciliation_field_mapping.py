"""
Canonical mapping between the exact IHX Excel headers and database attributes.

Do not rename Excel headers here unless the portal export itself changes.
"""

IHX_RECONCILIATION_FIELD_MAPPING = {
    "IHX Ref Id": "ihx_ref_id",
    "Hospital Name": "hospital_name",
    "RohiniId": "rohini_id",
    "Patient Name": "patient_name",
    "Patient Contact": "patient_contact",
    "In Patient Number": "in_patient_number",
    "Member/Customer ID": "member_customer_id",
    "Date of Admission": "date_of_admission",
    "Date of Discharge": "date_of_discharge",
    "TPA Name": "tpa_name",
    "Insurance Company Name": "insurance_company_name",
    "Policy Number": "policy_number",
    "Claim Number": "claim_number",
    "Initial Claim Number": "initial_claim_number",
    "Claim Creation Date": "claim_creation_date",
    "Claimed Amount": "claimed_amount",
    "Approved Amount": "approved_amount",
    "Copay": "copay",
    "Shortfall Amount": "shortfall_amount",
    "Hospital Discount": "hospital_discount",
    "Patient Paid Amount": "patient_paid_amount",
    "Settled Amount": "settled_amount",
    "TDS Amount": "tds_amount",
    "Cheque/ NEFT/ UTR No.": "cheque_neft_utr_number",
    "Cheque/ NEFT/ UTR Date": "cheque_neft_utr_date",
    "ReceiptNo": "receipt_number",
    "Claim Status": "claim_status",
    "Document Submission Date (on IHX)": "document_submission_date",
    "Payment Update Date": "payment_update_date",
    "Treatment": "treatment",
    "Diagnosis": "diagnosis",
    "Policy Type (Base/Top-up)": "policy_type",
    "Policy Holder Name": "policy_holder_name",
    "Employee Code": "employee_code",
    "InsurerComments": "insurer_comments",
    "UHID": "uhid",
    "InvoiceNumber": "invoice_number",
    "Courier Agency": "courier_agency",
    "Courier Destination": "courier_destination",
    "Courier Dispatch Date": "courier_dispatch_date",
    "Courier Name": "courier_name",
    "Courier Provider": "courier_provider",
    "Courier TrackId": "courier_track_id",
}

EXPECTED_IHX_HEADERS = tuple(IHX_RECONCILIATION_FIELD_MAPPING.keys())

DATE_FIELDS = {
    "date_of_admission",
    "date_of_discharge",
    "claim_creation_date",
    "cheque_neft_utr_date",
    "document_submission_date",
    "payment_update_date",
    "courier_dispatch_date",
}

DECIMAL_FIELDS = {
    "claimed_amount",
    "approved_amount",
    "copay",
    "shortfall_amount",
    "hospital_discount",
    "patient_paid_amount",
    "settled_amount",
    "tds_amount",
}
