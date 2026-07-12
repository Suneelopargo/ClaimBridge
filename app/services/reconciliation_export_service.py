from app.reports.reconciliation_excel_report import ReconciliationExcelReport
from app.services.reconciliation_field_catalog import get_exportable_field_metadata
from app.services.reconciliation_record_service import ReconciliationRecordService


class ReconciliationExportError(Exception):
    pass


class ReconciliationExportService:
    def __init__(self, db):
        self.record_service = ReconciliationRecordService(db)
        self.report = ReconciliationExcelReport()

    def export(self, request):
        try:
            metadata = get_exportable_field_metadata(request.fields)
        except ValueError as exc:
            raise ReconciliationExportError(str(exc)) from exc

        records = self._load_all(request.filters)
        records = self._sort(records, request.sort)
        return self.report.generate(request.report_name, metadata, records), len(records)

    def _load_all(self, filters):
        page, page_size, items = 1, 200, []
        common = {
            "search": filters.get("search"),
            "claim_status": filters.get("claimStatus"),
            "insurer": filters.get("insuranceCompany"),
            "tpa": filters.get("payorCompanyName"),
            "hospital_name": filters.get("hospitalName"),
        }
        while True:
            result = self.record_service.get_records(page=page, page_size=page_size, **common)
            items.extend(result["items"])
            if page >= result["totalPages"]:
                break
            page += 1
        return items

    @staticmethod
    def _sort(records, sort_items):
        result = list(records)
        for item in reversed(sort_items):
            result.sort(
                key=lambda row: (row.get(item.field) is None, row.get(item.field)),
                reverse=(item.direction == "desc"),
            )
        return result
