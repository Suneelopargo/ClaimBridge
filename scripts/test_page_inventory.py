
from app.services.sweet_engine.context_resolver import (
    ContextResolver,
)
from app.services.sweet_engine.page_inventory import (
    PageInventory,
)


def main() -> None:
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
                "Contains clinical content but no visible heading"
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
                "Billing table present but heading not visible"
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

    print("\nBefore context resolution")
    print(inventory.summary())

    resolver = ContextResolver()
    decisions = resolver.resolve_inventory(inventory)

    print("\nContext decisions")

    for decision in decisions:
        print(
            {
                "pageNumber": decision.page_number,
                "resolved": decision.resolved,
                "documentType": decision.document_type,
                "score": round(decision.score, 2),
                "reasons": decision.reasons,
            }
        )

    print("\nAfter context resolution")
    print(inventory.summary())

    print("\nPage results")

    for page in inventory.pages:
        print(
            page.page_number,
            page.raw_document_type,
            page.final_document_type,
            page.status.value,
            page.classification_source.value,
            page.review.required,
        )

    inventory.assert_no_page_drop()


if __name__ == "__main__":
    main()