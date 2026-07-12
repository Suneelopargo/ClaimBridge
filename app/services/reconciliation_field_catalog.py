CUSTOMER_RECONCILIATION_FIELDS = [
    {"field":"ihxRefId","displayName":"IHX Ref ID","source":"IHX","dataType":"string","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":140,"category":"Claim"},
    {"field":"uhid","displayName":"UHID","source":"IHX","dataType":"string","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":True,"width":120,"category":"Patient"},
    {"field":"patientName","displayName":"Patient Name","source":"IHX","dataType":"string","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":True,"width":220,"category":"Patient"},
    {"field":"admissionNumber","displayName":"Admission Number","source":"DERIVED","dataType":"string","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":True,"width":150,"category":"Admission"},
    {"field":"admittedDate","displayName":"Admitted Date","source":"IHX","dataType":"date","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":True,"width":130,"category":"Admission"},
    {"field":"dischargedDate","displayName":"Discharged Date","source":"IHX","dataType":"date","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":True,"width":130,"category":"Admission"},
    {"field":"insuranceCompany","displayName":"Insurance Company","source":"IHX","dataType":"string","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":True,"width":220,"category":"Payer"},
    {"field":"payorCompanyName","displayName":"Payor Company Name","source":"IHX","dataType":"string","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":True,"width":220,"category":"Payer"},
    {"field":"policyNumber","displayName":"Policy Number","source":"IHX","dataType":"string","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":160,"category":"Payer"},
    {"field":"claimAuthNumber","displayName":"Claim / Auth Number","source":"IHX","dataType":"string","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":True,"width":160,"category":"Claim"},
    {"field":"billNumber","displayName":"Bill Number","source":"DERIVED","dataType":"string","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":True,"width":140,"category":"Billing"},
    {"field":"billDate","displayName":"Bill Date","source":"MANUAL","dataType":"date","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":120,"category":"Billing"},
    {"field":"billAmount","displayName":"Bill Amount","source":"DERIVED","dataType":"decimal","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":True,"width":130,"category":"Financial"},
    {"field":"payorAmount","displayName":"Payor Amount","source":"DERIVED","dataType":"decimal","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":True,"width":130,"category":"Financial"},
    {"field":"patientAmount","displayName":"Patient Amount","source":"DERIVED","dataType":"decimal","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":130,"category":"Financial"},
    {"field":"copay","displayName":"Co-pay","source":"IHX","dataType":"decimal","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":110,"category":"Financial"},
    {"field":"hospitalDiscount","displayName":"Hospital Discount","source":"IHX","dataType":"decimal","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":140,"category":"Financial"},
    {"field":"totalDiscountAmount","displayName":"Total Discount Amount","source":"DERIVED_OR_MANUAL","dataType":"decimal","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":160,"category":"Financial"},
    {"field":"payorDiscount","displayName":"Payor Discount","source":"MANUAL","dataType":"decimal","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":140,"category":"Financial"},
    {"field":"patientDiscount","displayName":"Patient Discount","source":"MANUAL","dataType":"decimal","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":140,"category":"Financial"},
    {"field":"payorNetAmount","displayName":"Payor Net Amount","source":"DERIVED_OR_MANUAL","dataType":"decimal","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":True,"width":140,"category":"Financial"},
    {"field":"patientNetAmount","displayName":"Patient Net Amount","source":"DERIVED_OR_MANUAL","dataType":"decimal","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":150,"category":"Financial"},
    {"field":"amountReceived","displayName":"Amount Received","source":"IHX","dataType":"decimal","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":True,"width":140,"category":"Financial"},
    {"field":"tds","displayName":"TDS","source":"IHX","dataType":"decimal","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":100,"category":"Financial"},
    {"field":"amountReceivable","displayName":"Amount Receivable","source":"DERIVED_OR_MANUAL","dataType":"decimal","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":True,"width":150,"category":"Financial"},
    {"field":"claimStatus","displayName":"Claim Status","source":"IHX","dataType":"string","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":True,"width":150,"category":"Claim"},
    {"field":"submissionDate","displayName":"Submission Date","source":"IHX","dataType":"date","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":130,"category":"Claim"},
    {"field":"utrChequeNumber","displayName":"UTR / Cheque Number","source":"IHX","dataType":"string","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":170,"category":"Payment"},
    {"field":"utrChequeDate","displayName":"UTR / Cheque Date","source":"IHX","dataType":"date","editable":False,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":130,"category":"Payment"},
    {"field":"receivedDate","displayName":"Received Date","source":"MANUAL","dataType":"date","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":120,"category":"Dispatch"},
    {"field":"modeOfDispatch","displayName":"Mode of Dispatch","source":"MANUAL","dataType":"string","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":150,"category":"Dispatch"},
    {"field":"waybillPodByHand","displayName":"Waybill / POD / By Hand","source":"MANUAL","dataType":"string","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":180,"category":"Dispatch"},
    {"field":"queryDate","displayName":"Query Date","source":"MANUAL","dataType":"date","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":120,"category":"Query"},
    {"field":"queryRaised","displayName":"Query Raised","source":"MANUAL","dataType":"string","editable":True,"filterable":True,"sortable":False,"exportable":True,"defaultVisible":False,"width":220,"category":"Query"},
    {"field":"queryRaisedDate","displayName":"Query Raised Date","source":"MANUAL","dataType":"date","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":130,"category":"Query"},
    {"field":"queryRevertDate","displayName":"Query Revert Date","source":"MANUAL","dataType":"date","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":130,"category":"Query"},
    {"field":"disallowanceAmount","displayName":"Disallowance Amount","source":"MANUAL","dataType":"decimal","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":150,"category":"Disallowance"},
    {"field":"remarksReason","displayName":"Remarks / Reason","source":"MANUAL","dataType":"string","editable":True,"filterable":True,"sortable":False,"exportable":True,"defaultVisible":False,"width":220,"category":"Disallowance"},
    {"field":"disallowContestable","displayName":"Disallow Contestable","source":"MANUAL","dataType":"boolean","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":150,"category":"Disallowance"},
    {"field":"statusOfDisallowance","displayName":"Status of Disallowance","source":"MANUAL","dataType":"string","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":170,"category":"Disallowance"},
    {"field":"escalationRaised","displayName":"Escalation Raised","source":"MANUAL","dataType":"string","editable":True,"filterable":True,"sortable":False,"exportable":True,"defaultVisible":False,"width":200,"category":"Disallowance"},
    {"field":"accountsSubmissionDate","displayName":"Accounts Submission Date","source":"MANUAL","dataType":"date","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":160,"category":"Finance"},
    {"field":"financeReceivedDate","displayName":"Received Date - Finance","source":"MANUAL","dataType":"date","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":150,"category":"Finance"},
    {"field":"sapSettledDate","displayName":"Settled Date - SAP","source":"MANUAL","dataType":"date","editable":True,"filterable":True,"sortable":True,"exportable":True,"defaultVisible":False,"width":140,"category":"Finance"},
    {"field":"financeRemarks","displayName":"Finance Remarks","source":"MANUAL","dataType":"string","editable":True,"filterable":True,"sortable":False,"exportable":True,"defaultVisible":False,"width":220,"category":"Finance"},
]

FIELD_METADATA_BY_NAME = {item["field"]: item for item in CUSTOMER_RECONCILIATION_FIELDS}


def get_exportable_field_metadata(field_names):
    invalid = [name for name in field_names if name not in FIELD_METADATA_BY_NAME or not FIELD_METADATA_BY_NAME[name]["exportable"]]
    if invalid:
        raise ValueError("Unsupported or non-exportable fields: " + ", ".join(invalid))
    return [FIELD_METADATA_BY_NAME[name] for name in field_names]
