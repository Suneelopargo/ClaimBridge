import json

from app.config import (
    CLAIM_PACKET_GROUPED_DIR,
    CLAIM_PACKET_SEGREGATED_DIR,
)

from app.document_processing.checklist_rules import (
    DISPATCH_CHECKLIST_RULES,
)


def validate_against_dispatch_checklist(
    claim_id: str | None = None,
    patient_folder: str | None = None,
):
    try:
        if patient_folder:
            manifest_path = (
                CLAIM_PACKET_GROUPED_DIR
                / patient_folder
                / "manifest.json"
            )
        elif claim_id:
            manifest_path = (
                CLAIM_PACKET_SEGREGATED_DIR
                / claim_id
                / "manifest.json"
            )
        else:
            return {
                "success": False,
                "source": "DISPATCH_CHECKLIST_VALIDATION",
                "error": "Either claim_id or patient_folder is required",
            }

        if not manifest_path.exists():
            return {
                "success": False,
                "source": "DISPATCH_CHECKLIST_VALIDATION",
                "error": f"Manifest not found: {manifest_path}",
            }

        with open(
            manifest_path,
            "r",
            encoding="utf-8",
        ) as file:
            manifest = json.load(file)

        detected_docs = manifest.get(
            "documentsDetected",
            [],
        )

        grouped_docs = manifest.get(
            "groupedDocuments",
            [],
        )

        validation_rows = []
        missing_required = 0
        available_required = 0

        for rule in DISPATCH_CHECKLIST_RULES:
            matched_group_files = [
                doc.get("outputFile")
                for doc in grouped_docs
                if doc.get("groupCode")
                in rule.get("groupCodes", [])
            ]

            matched_page_files = [
                doc.get("outputFile")
                for doc in detected_docs
                if doc.get("documentType")
                in rule["documentTypes"]
            ]

            matched_files = (
                matched_group_files
                or matched_page_files
            )

            matched_files = [
                file_name
                for file_name in matched_files
                if file_name
            ]

            if matched_files:
                status = "AVAILABLE"

                if rule["required"]:
                    available_required += 1

                remarks = (
                    "Grouped packet available"
                    if matched_group_files
                    else (
                        "Multiple pages/documents found"
                        if len(matched_files) > 1
                        else "Document found"
                    )
                )
            else:
                status = (
                    "MISSING"
                    if rule["required"]
                    else "NOT_AVAILABLE"
                )

                if rule["required"]:
                    missing_required += 1

                remarks = (
                    "Required document not found"
                    if rule["required"]
                    else "Optional document not found"
                )

            validation_rows.append({
                "itemNo": rule["itemNo"],
                "checklistItem": rule["checklistItem"],
                "required": rule["required"],
                "expectedDocumentTypes": (
                    rule["documentTypes"]
                ),
                "groupCodes": rule.get(
                    "groupCodes",
                    [],
                ),
                "status": status,
                "matchedFiles": matched_files,
                "matchCount": len(matched_files),
                "remarks": remarks,
            })

        review_required_pages = [
            {
                "pageNumber": doc.get(
                    "pageNumber"
                ),
                "outputFile": doc.get(
                    "outputFile"
                ),
                "documentType": doc.get(
                    "documentType"
                ),
                "reason": doc.get(
                    "reason",
                    "",
                ),
                "confidence": doc.get(
                    "confidence"
                ),
            }
            for doc in detected_docs
            if (
                doc.get("reviewRequired")
                or doc.get("documentType")
                == "UNKNOWN"
            )
        ]

        total_required = len([
            rule
            for rule in DISPATCH_CHECKLIST_RULES
            if rule["required"]
        ])

        readiness_percent = round(
            (
                available_required
                / total_required
            )
            * 100
        )

        overall_status = (
            "READY"
            if (
                missing_required == 0
                and len(review_required_pages) == 0
            )
            else "REVIEW_REQUIRED"
        )

        result = {
            "claimId": manifest.get("claimId"),
            "patientName": manifest.get(
                "patientName"
            ),
            "patientFolder": manifest.get(
                "patientFolder"
            ),
            "sourceManifest": str(
                manifest_path
            ),
            "summary": {
                "totalChecklistItems": len(
                    DISPATCH_CHECKLIST_RULES
                ),
                "totalRequired": total_required,
                "availableRequired": (
                    available_required
                ),
                "missingRequired": (
                    missing_required
                ),
                "reviewRequiredPages": len(
                    review_required_pages
                ),
                "readinessPercent": (
                    readiness_percent
                ),
                "overallStatus": (
                    overall_status
                ),
            },
            "checklistValidation": (
                validation_rows
            ),
            "reviewRequiredPages": (
                review_required_pages
            ),
            "groupedDocuments": grouped_docs,
        }

        validation_output_path = (
            manifest_path.parent
            / "dispatch_checklist_validation.json"
        )

        with open(
            validation_output_path,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                result,
                file,
                indent=2,
            )

        return {
            "success": True,
            "source": "DISPATCH_CHECKLIST_VALIDATION",
            "result": result,
        }

    except Exception as exc:
        return {
            "success": False,
            "source": "DISPATCH_CHECKLIST_VALIDATION",
            "error": str(exc),
        }