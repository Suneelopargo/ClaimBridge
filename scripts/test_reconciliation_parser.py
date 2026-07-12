import sys
from pathlib import Path

from app.parsers.reconciliation_excel_parser import (
    ReconciliationExcelParser,
    ReconciliationParserError,
)


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: python scripts/test_reconciliation_parser.py "
            "<path-to-reconciliation.xlsx>"
        )
        return 2

    workbook_path = Path(sys.argv[1])
    parser = ReconciliationExcelParser()

    try:
        result = parser.parse(workbook_path)
    except ReconciliationParserError as exc:
        print(f"Parser failed: {exc}")
        return 1

    print(f"File: {result.source_file_name}")
    print(f"Sheet: {result.sheet_name}")
    print(f"Excel rows: {result.total_excel_rows}")
    print(f"Parsed rows: {result.successful_rows}")
    print(f"Blank rows: {result.skipped_blank_rows}")
    print(f"Failed rows: {result.failed_rows}")

    if result.parsed_rows:
        first = result.parsed_rows[0]
        print(f"First IHX Ref Id: {first.ihx_ref_id}")
        print(f"First source row: {first.source_row_number}")
        print(f"First change hash: {first.change_hash}")
        print(f"Parsed field count: {len(first.values)}")

    if result.row_errors:
        print("\nRow errors:")
        for error in result.row_errors[:20]:
            print(
                f"  Row {error.source_row_number}: "
                f"{error.message}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
