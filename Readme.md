# India Claims Automation Platform

Enterprise-grade Healthcare Claims Automation Platform for HCG Hospitals.

## Technology Stack

- FastAPI
- ReactJS
- PostgreSQL
- Playwright
- Microsoft Graph API

## Status

Sprint 1 - Foundation

ClaimsBridge Phase 2 — Step 1
This package adds:
`reconciliation_import_batch`
`reconciliation_summary`
an exact 43-column IHX Excel-to-model mapping
Apply
Copy:
`app/models/reconciliation_import_batch.py`
`app/models/reconciliation_summary.py`
`app/parsers/__init__.py`
`app/parsers/reconciliation_field_mapping.py`
Then update `create_tables.py` using `create_tables.py.patch`.
Create the tables

From the project root:
```powershell
python create_tables.py
python seed_master_data.py
```
Expected output:
```text
Tables created successfully
```
Then verify PostgreSQL contains:
```text
reconciliation_import_batch
reconciliation_summary
```
Design rules
All 43 IHX export fields are stored.
`portal_connection_id + ihx_ref_id` is unique.
Manual customer fields are not mixed into the IHX import model in this step.
Existing records will later be updated only for IHX-owned fields.
Missing rows in a later export will not be deleted automatically.

ClaimsBridge Phase 2 – IHX reconciliation download
Files to add
`app/connectors/ihx/reconciliation_connector.py`
`app/routers/reconciliation_router.py`
Replace/update:
`app/connectors/ihx/selectors.py`
`app/config.py`
`app/main.py`
`.env.example`
`.gitignore`
Endpoint
```http
POST /api/reconciliation/download
```
The endpoint:
Starts Playwright.
Uses the existing IHX username/password and Microsoft Graph OTP login.
Opens Reporting and Analytics / Reconciliation.
Locates the embedded Power BI report.
Opens Export data.
Selects Data with current layout.
Saves the `.xlsx` file under the configured download directory.
Run
```powershell
uvicorn app.main:app --reload
```
Open Swagger:
```text
http://127.0.0.1:8000/docs
```
Call:
```text
POST /api/reconciliation/download
```
Keep `headless=False` for the first test. After the selectors are verified on the
live IHX portal, it can be moved to an environment setting.
Important first-test observation
Power BI may place the export menu inside a different visual or iframe depending
on the report version. If the request fails, inspect the generated screenshot in:
```text
screenshots/ihx/
```
The returned API error includes the exact stage that failed.

ClaimsBridge Phase 2 — Step 2: Excel parser
This step adds a database-independent parser for the complete 43-column IHX
Power BI reconciliation export.
Copy
```text
app/parsers/reconciliation_excel_parser.py
scripts/test_reconciliation_parser.py
```
The parser uses the field mapping created in Step 1:
```text
app/parsers/reconciliation_field_mapping.py
```
Test against the downloaded report
From the project root:
```powershell
python scripts/test_reconciliation_parser.py data\reconciliation\downloads\ihx_reconciliation_20260711_174042.xlsx
```
Expected output resembles:
```text
File: ihx_reconciliation_20260711_174042.xlsx
Sheet: Export
Excel rows: ...
Parsed rows: ...
Blank rows: 0
Failed rows: 0
First IHX Ref Id: ...
Parsed field count: 43
```
Behaviour
Parses the full workbook every time.
Validates all 43 exact IHX headers.
Skips fully blank rows.
Requires `IHX Ref Id` for every data row.
Converts dates to `datetime.date`.
Converts financial values to `Decimal`.
Normalizes blank-like values to `None`.
Generates a SHA-256 hash from all 43 IHX-owned values.
Performs no database operations.
The hash will be used by the service to determine whether an existing database
record has actually changed.

ClaimsBridge Phase 2 — Step 3: Import API
This step adds the production code path:
```text
POST /api/reconciliation/import
    -> locate latest downloaded workbook
    -> parse all 43 columns
    -> compare by portal_connection_id + IHX Ref Id
    -> insert new records
    -> update changed records
    -> mark unchanged records as seen
    -> create import batch audit
    -> return statistics
```
Copy
```text
app/repositories/reconciliation_repository.py
app/services/reconciliation_service.py
```
Replace the current file with the supplied combined router:
```text
app/routers/reconciliation_router.py
```
The combined router preserves the already-working endpoint:
```http
POST /api/reconciliation/download
```
and adds:
```http
POST /api/reconciliation/import
```
Run
Restart manually without `--reload`:
```powershell
uvicorn app.main:app
```
Open Swagger:
```text
http://127.0.0.1:8000/docs
```
First call:
```http
POST /api/reconciliation/import
```
Expected first import:
```json
{
  "success": true,
  "batchId": 1,
  "fileName": "ihx_reconciliation_....xlsx",
  "totalRows": 1001,
  "inserted": 1001,
  "updated": 0,
  "unchanged": 0,
  "failed": 0,
  "skippedBlankRows": 0,
  "durationSeconds": 1.234,
  "rowErrors": []
}
```
Call it again without downloading a new file. Expected:
```json
{
  "inserted": 0,
  "updated": 0,
  "unchanged": 1001
}
```
Important
Ensure `.env` contains:
```env
IHX_PORTAL_CONNECTION_ID=1
IHX_RECONCILIATION_DOWNLOAD_DIR=data/reconciliation/downloads
```
The referenced `portal_connection` row must already exist. The import does not
delete records that are absent from a later export.

ClaimsBridge Phase 2 — Step 4: Customer-facing APIs
New APIs
```http
GET /api/reconciliation/report-fields
GET /api/reconciliation/records
GET /api/reconciliation/records/{id}
PATCH /api/reconciliation/records/{id}/manual-fields
```
Apply
Copy the new files.
Add the supplied relationship to `ReconciliationSummary`.
Import `ReconciliationManualDetails` in `create_tables.py`, then run:
```powershell
python create_tables.py
```
Verify table:
```text
reconciliation_manual_details
```
Register `reconciliation_query_router` in `main.py`.
Restart without reload:
```powershell
uvicorn app.main:app
```
First tests
```http
GET /api/reconciliation/report-fields
```
```http
GET /api/reconciliation/records?page=1&page_size=25
```
Example manual update:
```http
PATCH /api/reconciliation/records/1/manual-fields
```
```json
{
  "mode_of_dispatch": "Courier",
  "received_date": "2026-07-12",
  "finance_remarks": "Awaiting SAP settlement",
  "updated_by": "UI User"
}
```
The next IHX import will not overwrite these manual values.
Formula caution
The current derived values are initial product defaults:
bill amount = claimed amount
payor amount = approved amount
patient amount = patient paid amount
total discount = manual override, otherwise hospital discount
payor net = approved amount - manual payor discount
patient net = patient paid amount - manual patient discount
amount receivable = approved amount - settled amount - TDS
These formulas should be confirmed with the customer before being described as
financially authoritative. Manual override fields are available where needed.

ClaimsBridge Step 5
Adds:
richer `/api/reconciliation/report-fields`
`POST /api/reconciliation/reports/export`
Example request:
```json
{
  "report_name": "Outstanding Claims",
  "fields": [
    "patientName",
    "claimAuthNumber",
    "insuranceCompany",
    "billAmount",
    "payorAmount",
    "amountReceivable",
    "claimStatus",
    "financeRemarks"
  ],
  "filters": {
    "claimStatus": "Approved"
  },
  "sort": [
    {"field": "patientName", "direction": "asc"}
  ]
}
```
The response is an `.xlsx` file. Selected field order is preserved.
Apply:
Copy all new files.
Replace `reconciliation_field_catalog.py`.
Apply `report_fields_router.patch`.
Register the router using `main.patch`.
Restart without `--reload`.

Apply these changes
1. Register the router in `main.py`
```python
from app.routers.reconciliation_filter_router import (
    router as reconciliation_filter_router,
)

app.include_router(reconciliation_filter_router)
```
2. New filter metadata endpoint
```http
GET /api/reconciliation/filter-options
```
Claim Status, Insurance Company, Payor Company and Hospital values are loaded
from distinct values currently stored in PostgreSQL.
3. New structured search endpoint
```http
POST /api/reconciliation/records/search
```
Example:
```json
{
  "page": 1,
  "page_size": 25,
  "filters": [
    {
      "field": "claimStatus",
      "operator": "in",
      "value": ["Claim Approved", "Settled"]
    },
    {
      "field": "patientName",
      "operator": "contains",
      "value": "kumar"
    },
    {
      "field": "billAmount",
      "operator": "gte",
      "value": 50000
    }
  ],
  "sort": [
    {
      "field": "patientName",
      "direction": "asc"
    }
  ]
}
```
The existing `GET /api/reconciliation/records` remains for simple pagination.
4. Update export request to use the same structured filters
Change `filters` in `ReconciliationReportExportRequest` to:
```python
from app.schemas.reconciliation_filter_schemas import (
    ReconciliationFilterCondition,
)

filters: list[ReconciliationFilterCondition] = Field(default_factory=list)
```
Inside the export service, page through
`ReconciliationStructuredQueryService.search(...)` and export the returned
`items`. This makes the screen and Excel export use identical filter logic.