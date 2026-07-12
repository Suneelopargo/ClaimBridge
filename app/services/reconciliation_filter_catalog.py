FILTERS = [
    {"field":"claimStatus","displayName":"Claim Status","controlType":"multi-select","operators":["eq","in"],"valueSource":"DATABASE"},
    {"field":"insuranceCompany","displayName":"Insurance Company","controlType":"multi-select","operators":["eq","in","contains"],"valueSource":"DATABASE"},
    {"field":"payorCompanyName","displayName":"Payor Company Name","controlType":"multi-select","operators":["eq","in","contains"],"valueSource":"DATABASE"},
    {"field":"hospitalName","displayName":"Hospital Name","controlType":"multi-select","operators":["eq","in","contains"],"valueSource":"DATABASE"},
    {"field":"patientName","displayName":"Patient Name","controlType":"text","operators":["eq","contains","startsWith"],"valueSource":None},
    {"field":"claimAuthNumber","displayName":"Claim / Auth Number","controlType":"text","operators":["eq","contains","startsWith"],"valueSource":None},
    {"field":"uhid","displayName":"UHID","controlType":"text","operators":["eq","contains","startsWith"],"valueSource":None},
    {"field":"billNumber","displayName":"Bill Number","controlType":"text","operators":["eq","contains","startsWith"],"valueSource":None},
    {"field":"admittedDate","displayName":"Admitted Date","controlType":"date-range","operators":["eq","gte","lte","between"],"valueSource":None},
    {"field":"dischargedDate","displayName":"Discharged Date","controlType":"date-range","operators":["eq","gte","lte","between"],"valueSource":None},
    {"field":"submissionDate","displayName":"Submission Date","controlType":"date-range","operators":["eq","gte","lte","between"],"valueSource":None},
    {"field":"billAmount","displayName":"Bill Amount","controlType":"number-range","operators":["eq","gte","lte","between"],"valueSource":None},
    {"field":"payorAmount","displayName":"Payor Amount","controlType":"number-range","operators":["eq","gte","lte","between"],"valueSource":None},
    {"field":"amountReceived","displayName":"Amount Received","controlType":"number-range","operators":["eq","gte","lte","between"],"valueSource":None},
    {"field":"amountReceivable","displayName":"Amount Receivable","controlType":"number-range","operators":["eq","gte","lte","between"],"valueSource":None},
    {"field":"financeRemarks","displayName":"Finance Remarks","controlType":"text","operators":["contains","isNull","isNotNull"],"valueSource":None},
]
BY_FIELD = {item["field"]: item for item in FILTERS}
