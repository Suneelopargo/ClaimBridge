# scripts/evaluate_hcg_inventory.py

from pathlib import Path

from app.services.sweet_engine.context_resolver import (
    ContextResolver,
)
from app.services.sweet_engine.evaluation import (
    EvaluationReportBuilder,
    PacketEvaluator,
    load_ground_truth,
)
from app.services.sweet_engine.page_inventory import (
    PageInventory,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

GROUND_TRUTH_PATH = (
    PROJECT_ROOT
    / "data"
    / "sweet_evaluation"
    / "ground_truth"
    / "TEST-PACKET-001.json"
)

REPORT_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "sweet_evaluation"
    / "reports"
)


def build_test_inventory() -> PageInventory:
    inventory = PageInventory(
        packet_id="TEST-PACKET-001",
        total_pages=5,
        source_pdf_path="sample.pdf",
    )

    inventory.initialize_pages()

    inventory.apply_vision_result(
        page_number=1,
        extracted_text=(
            "Discharge Summary Diagnosis Hospital Course"
        ),
        classification={
            "documentType": "DISCHARGE_SUMMARY",
            "confidence": 0.96,
            "reason": "Visible discharge summary heading",
            "patientName": "Ramesh Kumar",
            "mrn": "MRN-1001",
        },
    )

    inventory.apply_vision_result(
        page_number=2,
        extracted_text=(
            "Treatment given and follow up advice"
        ),
        classification={
            "documentType": "DISCHARGE_SUMMARY",
            "confidence": 0.62,
            "reason": (
                "Clinical content without visible heading"
            ),
            "patientName": "Ramesh Kumar",
            "mrn": "MRN-1001",
        },
    )

    inventory.apply_vision_result(
        page_number=3,
        extracted_text=(
            "Condition at discharge and follow up"
        ),
        classification={
            "documentType": "DISCHARGE_SUMMARY",
            "confidence": 0.93,
            "reason": "Contains discharge advice",
            "patientName": "Ramesh Kumar",
            "mrn": "MRN-1001",
        },
    )

    inventory.apply_vision_result(
        page_number=4,
        extracted_text=(
            "Quantity Rate Amount Net Amount"
        ),
        classification={
            "documentType": "FINAL_HOSPITAL_BILL",
            "confidence": 0.64,
            "reason": (
                "Billing table present but heading absent"
            ),
            "patientName": "Ramesh Kumar",
            "billNumber": "BILL-2001",
        },
    )

    inventory.apply_vision_result(
        page_number=5,
        extracted_text=(
            "Final Bill Total Amount Net Amount"
        ),
        classification={
            "documentType": "FINAL_HOSPITAL_BILL",
            "confidence": 0.95,
            "reason": "Final bill heading and totals visible",
            "patientName": "Ramesh Kumar",
            "billNumber": "BILL-2001",
        },
    )

    ContextResolver().resolve_inventory(inventory)

    return inventory


def main() -> None:
    inventory = build_test_inventory()
    ground_truth = load_ground_truth(
        GROUND_TRUTH_PATH
    )

    evaluator = PacketEvaluator()
    report = evaluator.evaluate(
        inventory=inventory,
        ground_truth=ground_truth,
    )

    builder = EvaluationReportBuilder()

    json_path = builder.write_json(
        report,
        REPORT_DIRECTORY
        / "TEST-PACKET-001-evaluation.json",
    )

    csv_path = builder.write_csv(
        report,
        REPORT_DIRECTORY
        / "TEST-PACKET-001-pages.csv",
    )

    print("\nEvaluation metrics")

    for key, value in report.metrics.to_dict().items():
        print(f"{key}: {value}")

    if report.warnings:
        print("\nWarnings")
        for warning in report.warnings:
            print(f"- {warning}")

    print(f"\nJSON report: {json_path}")
    print(f"CSV report:  {csv_path}")


if __name__ == "__main__":
    main()