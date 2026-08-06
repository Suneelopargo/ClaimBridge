import logging

from pdf2image import convert_from_bytes
import tempfile
import os
import base64

from fastapi import UploadFile, File
from pypdf import PdfReader, PdfWriter

from app.config import (
    CLAIM_PACKET_GROUPED_DIR,
    CLAIM_PACKET_INPUT_DIR,
    CLAIM_PACKET_SEGREGATED_DIR,
)

from app.services.sweet_engine.adapters.hcg_packet_adapter import (
    build_inventory_from_packet_manifest,
)
from app.services.sweet_engine.classify_and_segregate_pipeline import (
    ClassifyAndSegregatePipeline,
)
from app.services.sweet_engine.document_registry import (
    allowed_document_types,
    document_family,
    is_standalone_document,
    normalize_document_type,
    normalize_page_role,
)

from dotenv import load_dotenv
from openai import OpenAI
from pathlib import Path
from typing import Any
from uuid import uuid4

import json
import re
import shutil
import uuid
from datetime import datetime
from fastapi import UploadFile
from pypdf import PdfReader
from collections import Counter

load_dotenv()
logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

INVALID_PATIENT_NAME_VALUES = {
            "",
            "unknown",
            "unknown patient",
            "not found",
            "na",
            "n/a",
            "none",
            "null",
            "ihx",
            "mediassist",
            "medi assist",
            "medibuddy",
            "fhpl",
            "vidal",
            "health india",
            "customer packet",
            "claim packet",
        }


def clean_metadata_value(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" :-|")

    # Stop when the next common field label begins.
    value = re.split(
        r"\b(?:Age|Gender|Sex|MRN|UHID|IP\s*No|Claim\s*No|Date)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()

    if len(value) < 3 or len(value) > 60:
        return ""

    return value.title()


def patient_name_from_filename(
    filename: str,
) -> str:
    stem = Path(filename).stem

    cleaned = re.sub(
        r"^[\d.\-_\s]+",
        "",
        stem,
    )

    cleaned = re.sub(
        r"[_\-]+",
        " ",
        cleaned,
    )

    cleaned = re.sub(
        r"\s+",
        " ",
        cleaned,
    ).strip()

    candidate = (
        cleaned.title()
        if cleaned
        else ""
    )

    if (
        not candidate
        or candidate.lower()
        in INVALID_PATIENT_NAME_VALUES
    ):
        return "Unknown Patient"

    return candidate


def _normalized_candidate_key(
        value: str | None,
) -> str:
    return re.sub(
        r"[^A-Z0-9]",
        "",
        str(value or "").upper(),
    )


def _consensus_vision_candidate(
        raw_docs: list[dict],
        field_name: str,
        minimum_occurrences: int = 2,
) -> str:
    candidates: list[str] = []

    for document in raw_docs:
        candidate_map = document.get(
            "visionIdentityCandidates",
            {},
        )

        if not isinstance(candidate_map, dict):
            continue

        value = str(
            candidate_map.get(field_name) or ""
        ).strip()

        if not value:
            continue

        if (
                field_name == "patientName"
                and value.lower()
                in INVALID_PATIENT_NAME_VALUES
        ):
            continue

        candidates.append(value)

    if not candidates:
        return ""

    normalized_to_original: dict[str, str] = {}
    normalized_candidates: list[str] = []

    for candidate in candidates:
        normalized = _normalized_candidate_key(
            candidate
        )

        if not normalized:
            continue

        normalized_candidates.append(
            normalized
        )
        normalized_to_original.setdefault(
            normalized,
            candidate,
        )

    if not normalized_candidates:
        return ""

    counts = Counter(normalized_candidates)
    normalized_value, occurrence_count = (
        counts.most_common(1)[0]
    )

    if occurrence_count < minimum_occurrences:
        return ""

    return normalized_to_original[
        normalized_value
    ]

def derive_packet_metadata(
    raw_docs: list[dict],
    all_text: str,
    filename: str,
    patient_name: str | None,
    claim_id: str | None,
) -> dict:
    """
    Derive metadata for any uploaded customer claim packet.

    Priority:
    1. Explicit caller input
    2. Vision-extracted page metadata
    3. PDF text labels
    4. Filename fallback
    5. Generated claim ID
    """

    final_patient_name = (patient_name or "").strip() or None
    final_claim_id = (claim_id or "").strip() or None
    # Use repeated Vision evidence only for packet identity.
    # These values remain non-authoritative at the individual-page level.
    if not final_patient_name:
        candidate = _consensus_vision_candidate(
            raw_docs=raw_docs,
            field_name="patientName",
            minimum_occurrences=2,
        )

        if candidate:
            final_patient_name = clean_metadata_value(
                candidate
            )

    if not final_claim_id:
        candidate = _consensus_vision_candidate(
            raw_docs=raw_docs,
            field_name="claimNumber",
            minimum_occurrences=2,
        )

        if not candidate:
            candidate = _consensus_vision_candidate(
                raw_docs=raw_docs,
                field_name="ipNumber",
                minimum_occurrences=2,
            )

        if candidate:
            final_claim_id = candidate
    invalid_values = {
        "",
        "unknown",
        "not found",
        "na",
        "n/a",
        "none",
        "null",
    }

    # 1. Patient name from Vision results
    if not final_patient_name:
        for doc in raw_docs:
            candidate = str(doc.get("patientName") or "").strip()

            if candidate.lower() not in invalid_values:
                final_patient_name = clean_metadata_value(candidate)
                if final_patient_name:
                    break

    # 2. Claim number / IP number / MRN from Vision results
    if not final_claim_id:
        for doc in raw_docs:
            candidate = (
                doc.get("claimNumber")
                or doc.get("ipNumber")
                or doc.get("mrn")
                or ""
            )

            candidate = str(candidate).strip()

            if candidate.lower() not in invalid_values:
                final_claim_id = candidate
                break

    # 3. Patient name from PDF text
    if not final_patient_name:
        patient_patterns = [
            r"Patient\s*Name\s*[:\-]\s*([A-Za-z][A-Za-z .]{2,60})",
            r"Name\s+of\s+(?:the\s+)?Patient\s*[:\-]\s*([A-Za-z][A-Za-z .]{2,60})",
            r"Patient\s*[:\-]\s*([A-Za-z][A-Za-z .]{2,60})",
            r"Insured\s+Name\s*[:\-]\s*([A-Za-z][A-Za-z .]{2,60})",
            r"Member\s+Name\s*[:\-]\s*([A-Za-z][A-Za-z .]{2,60})",
        ]

        for pattern in patient_patterns:
            match = re.search(pattern, all_text, re.IGNORECASE)

            if match:
                candidate = clean_metadata_value(match.group(1))

                if candidate:
                    final_patient_name = candidate
                    break

    # 4. Claim/IP/MRN from PDF text
    if not final_claim_id:
        claim_patterns = [
            r"Claim\s*(?:No|Number|ID)\s*[:\-]\s*([A-Za-z0-9\/\-]+)",
            r"IP\s*(?:No|Number)\s*[:\-]\s*([A-Za-z0-9\/\-]+)",
            r"MRN\s*[:\-]\s*([A-Za-z0-9\/\-]+)",
            r"UHID\s*[:\-]\s*([A-Za-z0-9\/\-]+)",
        ]

        for pattern in claim_patterns:
            match = re.search(pattern, all_text, re.IGNORECASE)

            if match:
                candidate = match.group(1).strip()

                if candidate:
                    final_claim_id = candidate
                    break

    # 5. Filename fallback
    if not final_patient_name:
        final_patient_name = patient_name_from_filename(filename)

    # 6. Generated claim ID fallback
    if not final_claim_id:
        final_claim_id = generate_claim_id()

    return {
        "patientName": final_patient_name or "Unknown Patient",
        "claimId": final_claim_id,
    }


def normalize_generic_packet_page(item: dict) -> dict:
    """
    Normalize a Vision page result using the canonical SWEET document
    registry.

    The raw Vision candidate is always preserved. A low confidence score
    no longer erases a supported candidate; it marks the page for review.
    """

    normalized = dict(item)

    raw_document_type = str(
        item.get("rawDocumentType")
        or item.get("documentType")
        or "UNKNOWN"
    ).strip()

    document_type = normalize_document_type(raw_document_type)

    try:
        confidence = float(item.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0

    normalized["rawDocumentType"] = raw_document_type.upper()
    normalized["documentType"] = document_type
    normalized["documentFamily"] = document_family(document_type)
    normalized["pageRole"] = normalize_page_role(
        item.get("pageRole")
    )
    normalized["standaloneDocument"] = bool(
        item.get("standaloneDocument")
        if item.get("standaloneDocument") is not None
        else is_standalone_document(document_type)
    )
    normalized["explicitDocumentStart"] = bool(
        item.get("explicitDocumentStart", False)
    )
    normalized["explicitDocumentEnd"] = bool(
        item.get("explicitDocumentEnd", False)
    )
    normalized["normalized"] = (
        document_type != raw_document_type.upper()
    )
    normalized["normalizationSource"] = (
        "SWEET_DOCUMENT_REGISTRY"
    )

    normalized["reviewRequired"] = (
        document_type == "UNKNOWN"
        or confidence < 0.70
        or normalized["pageRole"] == "UNKNOWN"
    )

    return normalized

def safe_folder_name(value: str):
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "unknown-patient"


def generate_claim_id():
    return "AUTO-CLM-" + datetime.now().strftime("%Y%m%d-%H%M%S")


def output_file_for_doc(document_type: str, page_number: int):
    name_map = {
        "COVERING_LETTER": "covering_letter",
        "CLAIM_FORM": "claim_form",
        "GIPSA_DECLARATION": "gipsa_declaration",
        "APPROVAL_LETTER": "approval_letter",
        "PREAUTHORIZATION_FORM": "preauthorization_form",
        "KYC_DOCUMENT": "kyc_document",
        "PATIENT_ID_PROOF": "patient_id_proof",
        "PATIENT_PHOTO": "patient_photo",
        "FINAL_HOSPITAL_BILL": "final_hospital_bill",
        "DETAILED_BILL_BREAKUP": "detailed_bill_breakup",
        "BILL_CONTINUATION": "bill_continuation",
        "DISCHARGE_SUMMARY": "discharge_summary",
        "PAYMENT_RECEIPT": "payment_receipt",
        "REFUND_RECEIPT": "refund_receipt",
        "CASE_PAPER": "case_paper",
        "OT_NOTES": "ot_notes",
        "INVESTIGATION_REPORT": "investigation_report",
        "LAB_REPORT": "lab_report",
        "RADIOLOGY_REPORT": "radiology_report",
        "PHARMACY_BILL": "pharmacy_bill",
        "PHARMACY_DETAILS": "pharmacy_details",
        "IMPLANT_STICKER_INVOICE": "implant_sticker_invoice",
        "CONSENT_FORM": "consent_form",
        "PRESCRIPTION": "prescription",
        "NON_MEDICAL_DETAILS": "non_medical_details",
        "CHECKLIST": "dispatch_checklist",
    }

    base = name_map.get(document_type, "review_required")
    return f"{page_number:02d}_{base}.pdf"


def normalize_person_name(
    value: str | None,
) -> str:
    if not value:
        return ""

    cleaned = re.sub(
        r"\b(MR|MRS|MS|DR|MASTER|SMT|SHRI)\b",
        " ",
        str(value).upper(),
    )

    return re.sub(
        r"[^A-Z]",
        "",
        cleaned,
    )


def patient_name_supported_by_text(
    patient_name: str | None,
    page_text: str | None,
) -> bool:
    normalized_name = normalize_person_name(
        patient_name
    )

    normalized_text = normalize_person_name(
        page_text
    )

    if not normalized_name or not normalized_text:
        return False

    return normalized_name in normalized_text


def validate_classification_identifiers(
    classification: dict,
    page_text: str,
) -> dict:
    rejected_identifiers = []

    identifier_fields = [
        "claimNumber",
        "mrn",
        "ipNumber",
        "billNumber",
        "authorizationNumber",
        "policyNumber",
        "memberId",
    ]

    # ---------------------------------------------------------
    # Text-readable PDF
    # ---------------------------------------------------------
    if page_text.strip():
        for field in identifier_fields:
            value = classification.get(field)

            if not value:
                continue

            if not identifier_exists_in_text(
                value=value,
                page_text=page_text,
            ):
                rejected_identifiers.append(
                    {
                        "field": field,
                        "value": value,
                        "reason": (
                            "Vision value not found in source page text"
                        ),
                    }
                )

                classification[field] = ""

        patient_name = classification.get("patientName")

        if (
            patient_name
            and not patient_name_supported_by_text(
                patient_name=patient_name,
                page_text=page_text,
            )
        ):
            rejected_identifiers.append(
                {
                    "field": "patientName",
                    "value": patient_name,
                    "reason": (
                        "Vision patient name not found "
                        "in source page text"
                    ),
                }
            )

            classification["patientName"] = ""

        classification["identifierVerificationStatus"] = (
            "VERIFIED_AGAINST_PDF_TEXT"
        )

    # ---------------------------------------------------------
    # Scanned / handwritten page
    # ---------------------------------------------------------
    else:
        fields_to_clear = [
            "patientName",
            *identifier_fields,
        ]

        for field in fields_to_clear:
            value = classification.get(field)

            if not value:
                continue

            rejected_identifiers.append(
                {
                    "field": field,
                    "value": value,
                    "reason": (
                        "Identifier cannot be verified because "
                        "the page has no extractable text"
                    ),
                }
            )

            classification[field] = ""

        classification["identifierVerificationStatus"] = (
            "UNVERIFIED_SCANNED_PAGE"
        )

    classification["rejectedIdentifiers"] = (
        rejected_identifiers
    )

    return classification


async def classify_and_segregate_claim_packet(
    file: UploadFile = File(...),
    claim_id: str | None = None,
    patient_name: str | None = None,
):
    """
    Classify and physically segregate an uploaded claim packet using
    the complete SWEET resolver chain.

    Flow:
    1. Save and render the uploaded PDF.
    2. Classify each page with Vision.
    3. Normalize page-level candidates without packet-specific rules.
    4. Write individual page PDFs and create the inventory manifest.
    5. Run Context, Identity, Boundary and DocumentGroup resolvers.
    6. Physically create one PDF per logical document group.
    7. Build checklist status and persist the final manifest.
    """

    temp_image_paths: list[str] = []

    try:
        # ---------------------------------------------------------
        # Step 1: Validate and save uploaded PDF
        # ---------------------------------------------------------
        safe_input_name = Path(
            file.filename or "customer-packet.pdf"
        ).name

        if Path(safe_input_name).suffix.lower() != ".pdf":
            raise ValueError("Only PDF claim packets are supported")

        CLAIM_PACKET_INPUT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Avoid overwriting an unrelated upload with the same name.
        upload_token = datetime.now().strftime("%Y%m%d%H%M%S%f")
        input_pdf_path = (
            CLAIM_PACKET_INPUT_DIR
            / f"{upload_token}_{safe_input_name}"
        )

        with input_pdf_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        reader = PdfReader(str(input_pdf_path))

        if not reader.pages:
            raise ValueError(
                "Uploaded PDF does not contain any pages"
            )

        images = convert_from_bytes(
            input_pdf_path.read_bytes(),
            dpi=180,
        )

        if len(images) != len(reader.pages):
            raise ValueError(
                "Unable to render every PDF page for classification"
            )

        raw_docs: list[dict] = []

        # ---------------------------------------------------------
        # Step 2: Classify every page with Vision
        # ---------------------------------------------------------
        for index, page in enumerate(reader.pages):
            page_number = index + 1
            page_text = page.extract_text() or ""

            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".png",
            ) as temp:
                image_path = temp.name
                images[index].save(image_path, "PNG")
                temp_image_paths.append(image_path)

            classification = classify_page_with_vision(
                image_path
            )

            # Preserve Vision output separately before verification clears
            # unsupported identifiers on scanned pages.
            vision_identity_candidates = {
                "patientName": str(
                    classification.get("patientName") or ""
                ).strip(),
                "claimNumber": str(
                    classification.get("claimNumber") or ""
                ).strip(),
                "ipNumber": str(
                    classification.get("ipNumber") or ""
                ).strip(),
                "mrn": str(
                    classification.get("mrn") or ""
                ).strip(),
            }

            classification = validate_classification_identifiers(
                classification=classification,
                page_text=page_text,
            )

            classification["visionIdentityCandidates"] = (
                vision_identity_candidates
            )
            # logger.warning(
            #     "PAGE %s -> %s",
            #     page_number,
            #     json.dumps(
            #         {
            #             "patientName": classification.get("patientName"),
            #             "claimNumber": classification.get("claimNumber"),
            #             "ipNumber": classification.get("ipNumber"),
            #             "status": classification.get("identifierVerificationStatus"),
            #             "rejected": classification.get("rejectedIdentifiers"),
            #         },
            #         indent=2,
            #     ),
            # )
            classification["source"] = "OPENAI_VISION"

            raw_document_type = str(
                classification.get("documentType")
                or "UNKNOWN"
            ).upper().strip()

            try:
                confidence = float(
                    classification.get("confidence") or 0
                )
            except (TypeError, ValueError):
                confidence = 0.0

            # Preserve the Vision candidate. Generic normalization and
            # EvidenceResolver decide whether it remains usable.
            raw_docs.append({
                "pageNumber": page_number,
                "documentType": raw_document_type,
                "rawDocumentType": raw_document_type,
                "documentFamily": classification.get(
                    "documentFamily", ""
                ),
                "visibleTitle": classification.get(
                    "visibleTitle", ""
                ),
                "sectionTitle": classification.get(
                    "sectionTitle", ""
                ),
                "pageRole": classification.get(
                    "pageRole", "UNKNOWN"
                ),
                "printedPageNumber": classification.get(
                    "printedPageNumber"
                ),
                "printedTotalPages": classification.get(
                    "printedTotalPages"
                ),
                "explicitDocumentStart": bool(
                    classification.get(
                        "explicitDocumentStart", False
                    )
                ),
                "explicitDocumentEnd": bool(
                    classification.get(
                        "explicitDocumentEnd", False
                    )
                ),
                "standaloneDocument": classification.get(
                    "standaloneDocument"
                ),
                "templateHint": classification.get(
                    "templateHint", ""
                ),
                "headerSignature": classification.get(
                    "headerSignature", ""
                ),
                "footerSignature": classification.get(
                    "footerSignature", ""
                ),
                "continuationIndicators": classification.get(
                    "continuationIndicators", []
                ),
                "candidateDocumentTypes": classification.get(
                    "candidateDocumentTypes", []
                ),
                "confidence": confidence,
                "source": classification.get("source"),
                "reason": classification.get("reason", ""),
                "patientName": classification.get(
                    "patientName", ""
                ),
                "claimNumber": classification.get(
                    "claimNumber", ""
                ),
                "mrn": classification.get("mrn", ""),
                "ipNumber": classification.get(
                    "ipNumber", ""
                ),
                "payerName": classification.get(
                    "payerName", ""
                ),
                "billNumber": classification.get(
                    "billNumber", ""
                ),
                "authorizationNumber": classification.get(
                    "authorizationNumber", ""
                ),
                "policyNumber": classification.get(
                    "policyNumber", ""
                ),
                "memberId": classification.get(
                    "memberId", ""
                ),
                "documentDate": classification.get(
                    "documentDate", ""
                ),
                "totalAmount": classification.get(
                    "totalAmount", ""
                ),
                "extractedText": page_text,
                "qualityStatus": (
                    "TEXT_READABLE"
                    if page_text.strip()
                    else "SCANNED_IMAGE"
                ),

                "visionIdentityCandidates": classification.get(
                    "visionIdentityCandidates",
                    {},
                ),
                "rejectedIdentifiers": classification.get(
                    "rejectedIdentifiers",
                    [],
                ),
                "identifierVerificationStatus": classification.get(
                    "identifierVerificationStatus",
                    "",
                ),
            })

        # ---------------------------------------------------------
        # Step 3: Derive packet metadata
        # ---------------------------------------------------------
        all_text = "\n".join(
            (page.extract_text() or "")
            for page in reader.pages
        )

        derived = derive_packet_metadata(
            raw_docs=raw_docs,
            all_text=all_text,
            filename=safe_input_name,
            patient_name=patient_name,
            claim_id=claim_id,
        )

        final_patient_name = derived["patientName"]
        final_claim_id = derived["claimId"]
        patient_folder = safe_folder_name(
            final_patient_name
        )

        segregated_dir = (
            CLAIM_PACKET_SEGREGATED_DIR
            / final_claim_id
        )
        grouped_output_root = (
            CLAIM_PACKET_GROUPED_DIR
            / patient_folder
        )

        if segregated_dir.exists():
            shutil.rmtree(segregated_dir)

        # PhysicalDocumentBuilder cleans only the packet-specific
        # directory, not the complete patient folder.
        packet_group_dir = (
            grouped_output_root / final_claim_id
        )
        if packet_group_dir.exists():
            shutil.rmtree(packet_group_dir)

        segregated_dir.mkdir(
            parents=True,
            exist_ok=True,
        )
        grouped_output_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        # ---------------------------------------------------------
        # Step 4: Normalize and write individual page PDFs
        # ---------------------------------------------------------
        detected_docs: list[dict] = []

        for item in raw_docs:
            normalized = normalize_generic_packet_page(item)
            normalized["outputFile"] = output_file_for_doc(
                normalized["documentType"],
                normalized["pageNumber"],
            )
            normalized["reviewRequired"] = (
                normalized["documentType"] == "UNKNOWN"
            )
            detected_docs.append(normalized)

        for item in detected_docs:
            page_index = item["pageNumber"] - 1
            segregated_file_path = (
                segregated_dir / item["outputFile"]
            )

            write_single_page_pdf(
                reader,
                page_index,
                segregated_file_path,
            )
            item["segregatedFile"] = str(
                segregated_file_path
            )

        # This manifest is the adapter input for PageInventory.
        inventory_manifest = {
            "claimId": final_claim_id,
            "packetId": final_claim_id,
            "patientName": final_patient_name,
            "patientFolder": patient_folder,
            "sourceFile": str(input_pdf_path),
            "segregatedFolder": str(segregated_dir),
            "totalPages": len(reader.pages),
            "documentsDetected": detected_docs,
        }

        inventory_manifest_path = (
            segregated_dir / "inventory_manifest.json"
        )
        with inventory_manifest_path.open(
            "w",
            encoding="utf-8",
        ) as manifest_file:
            json.dump(
                inventory_manifest,
                manifest_file,
                indent=2,
                ensure_ascii=False,
            )

        # ---------------------------------------------------------
        # Step 5: Run the current SWEET resolver chain and perform
        # physical document grouping.
        # ---------------------------------------------------------
        inventory = build_inventory_from_packet_manifest(
            inventory_manifest,
            run_context_resolution=True,
        )

        pipeline_result = (
            ClassifyAndSegregatePipeline().run(
                inventory=inventory,
                source_pdf=input_pdf_path,
                output_root=grouped_output_root,
            )
        )

        claim_pack_dir = Path(
            pipeline_result.output_directory
        )

        grouped_documents = [
            {
                "groupId": document["groupId"],
                "groupCode": document["documentType"],
                "displayName": document["documentType"].replace(
                    "_", " "
                ).title(),
                "documentType": document["documentType"],
                "documentFamily": document[
                    "documentFamily"
                ],
                "outputFile": document["fileName"],
                "filePath": document["filePath"],
                "pageNumbers": document["sourcePages"],
                "pageCount": document["pageCount"],
                "confidence": document["confidence"],
                "status": document["status"],
                "reviewFlags": document["reviewFlags"],
            }
            for document in pipeline_result.documents
        ]

        # ---------------------------------------------------------
        # Step 6: Build checklist status from final physical groups
        # ---------------------------------------------------------
        checklist_status = build_dispatch_checklist_status(
            detected_docs=detected_docs,
            grouped_docs=grouped_documents,
        )

        review_required_pages = [
            {
                "pageNumber": item.get("pageNumber"),
                "outputFile": item.get("outputFile"),
                "documentType": item.get("documentType"),
                "rawDocumentType": item.get(
                    "rawDocumentType"
                ),
                "confidence": item.get("confidence"),
                "reason": item.get("reason", ""),
            }
            for item in detected_docs
            if item.get("reviewRequired")
        ]

        review_required_groups = [
            group
            for group in grouped_documents
            if group.get("status") == "REVIEW"
        ]

        identified_pages = sum(
            1
            for item in detected_docs
            if item.get("documentType") != "UNKNOWN"
        )

        # ---------------------------------------------------------
        # Step 7: Build and save the final API manifest
        # ---------------------------------------------------------
        manifest = {
            "claimId": final_claim_id,
            "packetId": final_claim_id,
            "patientName": final_patient_name,
            "patientFolder": patient_folder,
            "sourceFile": str(input_pdf_path),
            "segregatedFolder": str(segregated_dir),
            "claimPackFolder": str(claim_pack_dir),
            "inventoryManifest": str(
                inventory_manifest_path
            ),
            "groupedManifest": (
                pipeline_result.grouped_manifest_path
            ),
            "totalPages": len(reader.pages),
            "documentsDetected": detected_docs,
            "groupedDocuments": grouped_documents,
            "checklistStatus": checklist_status,
            "reviewRequiredPages": review_required_pages,
            "reviewRequiredGroups": review_required_groups,
            "logicalGroupingIntegrityValid": (
                pipeline_result
                .logical_grouping_integrity_valid
            ),
            "physicalGroupingIntegrityValid": (
                pipeline_result
                .physical_grouping_integrity_valid
            ),
            "summary": {
                "totalPages": len(reader.pages),
                "identifiedPages": identified_pages,
                "groupedDocumentCount": len(
                    grouped_documents
                ),
                "reviewRequiredPages": len(
                    review_required_pages
                ),
                "reviewRequiredGroups": len(
                    review_required_groups
                ),
                "status": (
                    "REVIEW_REQUIRED"
                    if (
                        review_required_pages
                        or review_required_groups
                    )
                    else "PROCESSED"
                ),
            },
        }

        segregated_manifest_path = (
            segregated_dir / "manifest.json"
        )
        claim_pack_manifest_path = (
            claim_pack_dir / "manifest.json"
        )

        for manifest_path in (
            segregated_manifest_path,
            claim_pack_manifest_path,
        ):
            with manifest_path.open(
                "w",
                encoding="utf-8",
            ) as manifest_file:
                json.dump(
                    manifest,
                    manifest_file,
                    indent=2,
                    ensure_ascii=False,
                )

        return {
            "success": True,
            "source": "SWEET_RESOLVER_PACKET_PROCESSING",
            "result": manifest,
        }

    except Exception as exc:
        print(
            "CLAIM PACKET PROCESSING ERROR:",
            repr(exc),
        )

        return {
            "success": False,
            "source": "SWEET_RESOLVER_PACKET_PROCESSING",
            "error": str(exc),
        }

    finally:
        for image_path in temp_image_paths:
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
            except Exception:
                pass

def classify_page_with_vision(image_path: str):
    base64_image = image_to_base64(image_path)

    allowed_types = ",\n".join(
        allowed_document_types()
    )

    prompt = f"""
You are extracting structured evidence from ONE page of a real Indian
hospital insurance claim packet.

The page may be scanned, handwritten, stamped, rotated, low quality, or
may contain only one section of a larger multi-page document.

Return STRICT JSON only. Do not use markdown.

Required JSON schema:
{{
  "documentType": "",
  "candidateDocumentTypes": [
    {{"type": "", "confidence": 0.0}}
  ],
  "documentFamily": "",
  "visibleTitle": "",
  "sectionTitle": "",
  "pageRole": "START|CONTINUATION|END|STANDALONE|UNKNOWN",
  "printedPageNumber": null,
  "printedTotalPages": null,
  "explicitDocumentStart": false,
  "explicitDocumentEnd": false,
  "standaloneDocument": false,
  "templateHint": "",
  "headerSignature": "",
  "footerSignature": "",
  "continuationIndicators": [],
  "patientName": "",
  "claimNumber": "",
  "mrn": "",
  "ipNumber": "",
  "payerName": "",
  "billNumber": "",
  "authorizationNumber": "",
  "policyNumber": "",
  "memberId": "",
  "documentDate": "",
  "totalAmount": "",
  "confidence": 0.0,
  "reason": ""
}}

Allowed documentType values:
{allowed_types}

Critical interpretation rules:

1. Classify the physical DOCUMENT PAGE, not every section mentioned in
   its body.

2. A payment/refund section inside a multi-page hospital bill remains
   BILL_CONTINUATION when page numbering, bill number, IP number,
   patient name, header, or template show that it belongs to the bill.

3. Deduction tables, package break-ups, payable amounts, medicine
   charges, investigation charges, authorization summaries, terms and
   conditions, or "documents to be provided" sections inside an
   authorization letter are AUTHORIZATION_CONTINUATION, not hospital
   bills or covering letters.

4. Sections such as:
   - TO BE FILLED BY TREATING DOCTOR/HOSPITAL
   - DETAILS OF PATIENT ADMITTED
   - DECLARATION BY PATIENT / REPRESENTATIVE
   - HOSPITAL DECLARATION
   - TERMS AND CONDITIONS
   are usually FORM_CONTINUATION when they are pages of an existing
   preauthorization/cashless form. Do not label them standalone
   TREATMENT_ORDER or GIPSA_DECLARATION unless the page is clearly a
   separate independent document.

5. A visible "Page X of Y" is strong evidence. Extract both numbers.
   Page 2 of 7 is normally CONTINUATION, not STANDALONE.

6. Use START only when the page visibly begins a document: explicit
   title/letter opening, printed page 1, new reference number, new form
   front page, or clearly independent card/receipt/report.

7. Use STANDALONE for an independent one-page receipt, ID card,
   covering letter, justification letter, checklist, or declaration.

8. Use END when the page visibly closes the document, is printed as the
   last page, contains final signatures/end-of-report, or completes a
   numbered sequence.

9. Do not invent missing identifiers. Use empty strings or null.

10. candidateDocumentTypes should contain up to three plausible types,
    ordered strongest first. documentType is the strongest candidate.

11. Confidence measures evidence strength. Do not erase a recognizable
    candidate merely because confidence is below 0.70.

12. visibleTitle must be the actual main visible heading. sectionTitle
    is a subsection heading and must not automatically determine the
    document type.

13. headerSignature/footerSignature should be short normalized visible
    identifiers useful for comparing adjacent pages, for example:
    patient|IP|bill number or insurer|authorization reference.

14. continuationIndicators should list concise visible evidence such
    as "page 3 of 7", "same bill number", "continued deduction table",
    "same authorization template", or "end of report".

Return exactly one JSON object.
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You extract structured evidence from scanned "
                    "healthcare claim packet pages. You distinguish "
                    "whole-document identity from subsection content."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": (
                                "data:image/png;base64,"
                                f"{base64_image}"
                            )
                        },
                    },
                ],
            },
        ],
        temperature=0,
    )

    try:
        result = clean_json_response(
            response.choices[0].message.content
        )

        if not isinstance(result, dict):
            raise ValueError(
                "Vision response is not a JSON object"
            )

        result["documentType"] = normalize_document_type(
            result.get("documentType")
        )
        result["documentFamily"] = document_family(
            result["documentType"]
        )
        result["pageRole"] = normalize_page_role(
            result.get("pageRole")
        )

        if not isinstance(
            result.get("continuationIndicators"),
            list,
        ):
            result["continuationIndicators"] = []

        if not isinstance(
            result.get("candidateDocumentTypes"),
            list,
        ):
            result["candidateDocumentTypes"] = []

        return result

    except Exception as exc:
        return {
            "documentType": "UNKNOWN",
            "candidateDocumentTypes": [],
            "documentFamily": "UNKNOWN",
            "visibleTitle": "",
            "sectionTitle": "",
            "pageRole": "UNKNOWN",
            "printedPageNumber": None,
            "printedTotalPages": None,
            "explicitDocumentStart": False,
            "explicitDocumentEnd": False,
            "standaloneDocument": False,
            "templateHint": "",
            "headerSignature": "",
            "footerSignature": "",
            "continuationIndicators": [],
            "confidence": 0.2,
            "reason": (
                "Vision response could not be parsed: "
                f"{exc}"
            ),
        }

def write_single_page_pdf(reader: PdfReader, page_index: int, output_path: Path):
    writer = PdfWriter()
    writer.add_page(reader.pages[page_index])

    with open(output_path, "wb") as f:
        writer.write(f)


def write_merged_pdf(reader: PdfReader, page_numbers: list[int], output_path: Path):
    writer = PdfWriter()

    for page_number in page_numbers:
        writer.add_page(reader.pages[page_number - 1])

    with open(output_path, "wb") as f:
        writer.write(f)


def build_grouped_documents(reader: PdfReader, detected_docs: list[dict], output_dir: Path):
    grouped_documents = []

    for group_code, rule in GROUPING_RULES.items():
        matched_pages = [
            doc["pageNumber"]
            for doc in detected_docs
            if doc.get("documentType") in rule["documentTypes"]
        ]

        if not matched_pages:
            continue

        matched_pages = sorted(set(matched_pages))
        output_path = output_dir / rule["outputFile"]

        write_merged_pdf(reader, matched_pages, output_path)

        grouped_documents.append({
            "groupCode": group_code,
            "displayName": rule["displayName"],
            "outputFile": rule["outputFile"],
            "filePath": str(output_path),
            "pageNumbers": matched_pages,
            "pageCount": len(matched_pages),
            "status": "AVAILABLE",
        })

    return grouped_documents


def build_dispatch_checklist_status(
        detected_docs: list[dict],
        grouped_docs: list[dict],
):
    checklist_status = []

    for rule in DISPATCH_CHECKLIST_RULES:
        matched_group_files = [
            doc.get("outputFile")
            for doc in grouped_docs
            if (
                doc.get("groupCode")
                in rule.get("groupCodes", [])
                or doc.get("documentType")
                in rule["documentTypes"]
            )
        ]

        matched_page_files = [
            doc.get("outputFile")
            for doc in detected_docs
            if doc.get("documentType") in rule["documentTypes"]
        ]

        matched_files = matched_group_files or matched_page_files
        matched_files = [f for f in matched_files if f]

        available = bool(matched_files)

        checklist_status.append({
            "itemNo": rule["itemNo"],
            "documentType": rule["checklistItem"].upper().replace(" ", "_").replace("/", "_"),
            "checklistItem": rule["checklistItem"],
            "required": rule["required"],
            "available": available,
            "status": "AVAILABLE" if available else ("MISSING" if rule["required"] else "NOT_AVAILABLE"),
            "matchedFiles": matched_files,
            "matchCount": len(matched_files),
        })

    return checklist_status


DISPATCH_CHECKLIST_RULES = [
    {
        "itemNo": "1",
        "checklistItem": "Claim Form",
        "required": True,
        "documentTypes": ["CLAIM_FORM"],
    },
    {
        "itemNo": "2",
        "checklistItem": "GIPSA / Insurance / TPA Declaration",
        "required": True,
        "documentTypes": ["GIPSA_DECLARATION"],
    },
    {
        "itemNo": "3",
        "checklistItem": "Approval / Referral Letter / GOP",
        "required": True,
        "documentTypes": [
            "APPROVAL_LETTER",
            "GOP_FINAL_APPROVAL",
            "CASHLESS_AUTHORIZATION_LETTER"
        ]
    },
    {
        "itemNo": "4",
        "checklistItem": "Preauthorization Form",
        "required": True,
        "documentTypes": ["PREAUTHORIZATION_FORM"],
    },
    {
        "itemNo": "5",
        "checklistItem": "KYC Details",
        "required": True,
        "documentTypes": [
            "KYC_DOCUMENT",
            "PATIENT_ID_PROOF",
            "PROPOSER_ID_PROOF"
        ],
    },
    {
        "itemNo": "6",
        "checklistItem": "Patient Photo ID Proof",
        "required": True,
        "documentTypes": ["PATIENT_ID_PROOF"],
    },
    {
        "itemNo": "7",
        "checklistItem": "Patient Photo",
        "required": True,
        "documentTypes": ["PATIENT_PHOTO"],
    },
    {
        "itemNo": "8",
        "checklistItem": "Final Bill Summary and Detailed Bill",
        "required": True,
        "documentTypes": [
            "FINAL_HOSPITAL_BILL",
            "DETAILED_BILL_BREAKUP",
            "BILL_CONTINUATION",
        ],
    },
    {
        "itemNo": "9",
        "checklistItem": "Discharge Summary",
        "required": True,
        "documentTypes": ["DISCHARGE_SUMMARY"],
    },
    {
        "itemNo": "10",
        "checklistItem": "Payment / Refund Receipt / Voucher",
        "required": True,
        "documentTypes": ["PAYMENT_RECEIPT", "REFUND_RECEIPT"],
    },
    {
        "itemNo": "11",
        "checklistItem": "Indoor Case Papers",
        "required": True,
        "documentTypes": ["CASE_PAPER", "OT_NOTES"],
    },
    {
        "itemNo": "13",
        "checklistItem": "Investigation Reports and Films",
        "required": True,
        "documentTypes": [
            "INVESTIGATION_REPORT",
            "LAB_REPORT",
            "RADIOLOGY_REPORT",
        ],
    },
    {
        "itemNo": "14",
        "checklistItem": "Implant Sticker with Invoice",
        "required": False,
        "documentTypes": ["IMPLANT_STICKER_INVOICE"],
    },
    {
        "itemNo": "15",
        "checklistItem": "Pharmacy Details",
        "required": True,
        "documentTypes": ["PHARMACY_DETAILS", "PHARMACY_BILL"],
    },
    {
        "itemNo": "16",
        "checklistItem": "Package / Profile Break-up",
        "required": True,
        "documentTypes": ["DETAILED_BILL_BREAKUP"],
    },
    {
        "itemNo": "18",
        "checklistItem": "Consent Forms",
        "required": True,
        "documentTypes": ["CONSENT_FORM"],
    },
    {
        "itemNo": "19",
        "checklistItem": "Prescription Details",
        "required": True,
        "documentTypes": ["PRESCRIPTION"],
    },
    {
        "itemNo": "20",
        "checklistItem": "Non-Medical Details",
        "required": False,
        "documentTypes": ["NON_MEDICAL_DETAILS"],
    },
]

GROUPING_RULES = {
    "FINAL_BILL_PACKET": {
        "displayName": "Final Bill Summary and Detailed Bill",
        "documentTypes": [
            "FINAL_HOSPITAL_BILL",
            "DETAILED_BILL_BREAKUP",
            "BILL_CONTINUATION",
        ],
        "outputFile": "final_bill_packet.pdf",
    },
    "GOP_APPROVAL_PACKET": {
        "displayName": "Approval / Referral Letter / GOP",
        "documentTypes": [
            "APPROVAL_LETTER",
            "GOP_PRE_APPROVAL",
            "GOP_FINAL_APPROVAL",
            "CASHLESS_AUTHORIZATION_LETTER",
        ],
        "outputFile": "gop_approval_packet.pdf",
    },
    "PREAUTHORIZATION_FORM_PACKET": {
        "displayName": "Preauthorization Form",
        "documentTypes": ["PREAUTHORIZATION_FORM"],
        "outputFile": "preauthorization_form_packet.pdf",
    },
    "KYC_PACKET": {
        "displayName": "KYC Details",
        "documentTypes": [
            "KYC_DOCUMENT",
            "PATIENT_ID_PROOF",
            "PROPOSER_ID_PROOF",
        ],
        "outputFile": "kyc_packet.pdf",
    },
    "PATIENT_ID_PROOF_PACKET": {
        "displayName": "Patient Photo ID Proof",
        "documentTypes": ["PATIENT_ID_PROOF"],
        "outputFile": "patient_id_proof_packet.pdf",
    },
    "DISCHARGE_SUMMARY_PACKET": {
        "displayName": "Discharge Summary",
        "documentTypes": ["DISCHARGE_SUMMARY"],
        "outputFile": "discharge_summary_packet.pdf",
    },
    "PAYMENT_RECEIPT_PACKET": {
        "displayName": "Payment / Refund Receipt / Voucher",
        "documentTypes": ["PAYMENT_RECEIPT", "REFUND_RECEIPT"],
        "outputFile": "payment_receipts_packet.pdf",
    },
    "REPORTS_PACKET": {
        "displayName": "Investigation Reports and Films",
        "documentTypes": [
            "INVESTIGATION_REPORT",
            "LAB_REPORT",
            "RADIOLOGY_REPORT",
        ],
        "outputFile": "investigation_reports_packet.pdf",
    },
    "PHARMACY_PACKET": {
        "displayName": "Pharmacy Details",
        "documentTypes": ["PHARMACY_DETAILS", "PHARMACY_BILL"],
        "outputFile": "pharmacy_packet.pdf",
    },
    "CONSENT_PACKET": {
        "displayName": "Consent Forms",
        "documentTypes": ["CONSENT_FORM"],
        "outputFile": "consent_forms_packet.pdf",
    },
    "PRESCRIPTION_PACKET": {
        "displayName": "Prescription Details",
        "documentTypes": ["PRESCRIPTION"],
        "outputFile": "prescription_packet.pdf",
    },
}


def image_to_base64(image_path: str):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def clean_json_response(content: str):
    content = content.strip()
    if content.startswith("```json"):
        content = content.replace("```json", "", 1)
    if content.startswith("```"):
        content = content.replace("```", "", 1)
    if content.endswith("```"):
        content = content[:-3]
    return json.loads(content.strip())


def validate_segregated_documents(claim_id: str = "IND-CLM-2026-00083"):
    try:
        folder = CLAIM_PACKET_SEGREGATED_DIR / claim_id

        if not folder.exists():
            return {
                "success": False,
                "source": "SEGREGATED_DOCUMENT_VALIDATION",
                "error": f"Folder not found: {folder}",
            }

        expected_documents = {
            "ADMISSION_NOTE": "01_admission_note.pdf",
            "PATIENT_CONSENT_FORM": "02_patient_consent_form.pdf",
            "OPERATION_THEATRE_NOTES": "03_operation_theatre_notes.pdf",
            "IMPLANT_VENDOR_INVOICE": "04_implant_vendor_invoice.pdf",
            "PHARMACY_BILL": "05_pharmacy_bill.pdf",
            "DOCTOR_PRESCRIPTION": "06_doctor_prescription.pdf",
            "DETAILED_BILL_BREAKUP": "07_detailed_bill_breakup.pdf",
            "FINAL_HOSPITAL_BILL": "08_final_hospital_bill.pdf",
            "DISCHARGE_SUMMARY": "09_discharge_summary.pdf",
        }

        checklist = []
        validations = []
        extracted_text_by_doc = {}

        for doc_type, filename in expected_documents.items():
            path = folder / filename
            available = path.exists()

            checklist.append({
                "documentType": doc_type,
                "fileName": filename,
                "available": available,
                "status": "AVAILABLE" if available else "MISSING",
            })

            if available:
                extracted_text_by_doc[doc_type] = read_pdf_text(path)
            else:
                validations.append(
                    validation_result(
                        "Checklist document availability",
                        doc_type,
                        "FAIL",
                        f"{filename} is missing",
                        "CRITICAL",
                    )
                )

        # 1. Checklist completion
        missing_docs = [item for item in checklist if not item["available"]]

        validations.append(
            validation_result(
                "MediAssist checklist completeness",
                "CLAIM_PACKET",
                "PASS" if not missing_docs else "FAIL",
                "All payer-required documents are available"
                if not missing_docs
                else f"Missing documents: {', '.join([d['documentType'] for d in missing_docs])}",
                "CRITICAL" if missing_docs else "INFO",
            )
        )

        # 2. Patient identity consistency
        patient_name_hits = [
            doc_type
            for doc_type, text in extracted_text_by_doc.items()
            if "Mohan Kumar".lower() in text.lower()
        ]

        validations.append(
            validation_result(
                "Patient identity consistency",
                "CLAIM_PACKET",
                "PASS" if len(patient_name_hits) >= 7 else "WARNING",
                f"Mohan Kumar found in {len(patient_name_hits)} documents",
                "CRITICAL" if len(patient_name_hits) < 5 else "INFO",
            )
        )

        # 3. Chronology validation
        all_text = "\n".join(extracted_text_by_doc.values())

        has_admission = "18-Jun-2026" in all_text
        has_surgery = "19-Jun-2026" in all_text
        has_discharge = "22-Jun-2026" in all_text

        validations.append(
            validation_result(
                "Admission-surgery-discharge chronology",
                "CLAIM_PACKET",
                "PASS" if has_admission and has_surgery and has_discharge else "WARNING",
                f"Admission: {'18-Jun-2026' if has_admission else 'Not found'} | "
                f"Surgery: {'19-Jun-2026' if has_surgery else 'Not found'} | "
                f"Discharge: {'22-Jun-2026' if has_discharge else 'Not found'}",
                "CRITICAL" if not has_admission or not has_discharge else "INFO",
            )
        )

        # 4. Consent form validation
        consent_text = extracted_text_by_doc.get("PATIENT_CONSENT_FORM", "")

        witness_signature_present = bool(
            re.search(r"Witness Signature\s+Signed", consent_text, re.IGNORECASE)
        )

        validations.append(
            validation_result(
                "Consent form witness signature",
                "PATIENT_CONSENT_FORM",
                "PASS" if witness_signature_present else "FAIL",
                "Witness signature available"
                if witness_signature_present
                else "Witness signature is missing / blank",
                "CRITICAL",
            )
        )

        # 5. Pharmacy linkage validation
        pharmacy_text = extracted_text_by_doc.get("PHARMACY_BILL", "")

        prescription_ref_present = bool(
            re.search(r"Prescription Ref\.\s+[A-Za-z0-9\-]+", pharmacy_text, re.IGNORECASE)
        )

        validations.append(
            validation_result(
                "Pharmacy bill prescription linkage",
                "PHARMACY_BILL",
                "PASS" if prescription_ref_present else "WARNING",
                "Prescription reference available"
                if prescription_ref_present
                else "Prescription reference is missing in pharmacy bill",
                "WARNING",
            )
        )

        # 6. Original / photocopy detection
        originality_results = []

        for doc_type, text in extracted_text_by_doc.items():
            has_original = contains_any(text, ["ORIGINAL", "Original Bill", "ORIGINAL FINAL BILL"])
            has_copy = contains_any(text, ["PHOTOCOPY", "DUPLICATE COPY", "COPY"])

            score = 50

            if has_original:
                score += 35

            if has_copy:
                score -= 50

            score = max(0, min(100, score))

            if has_copy:
                status = "WARNING"
                classification = "PHOTOCOPY_RISK"
                severity = "WARNING"
            elif score >= 75:
                status = "PASS"
                classification = "ORIGINAL_LIKELY"
                severity = "INFO"
            else:
                status = "WARNING"
                classification = "ORIGINALITY_UNCERTAIN"
                severity = "WARNING"

            originality_results.append({
                "documentType": doc_type,
                "originalityScore": score,
                "classification": classification,
            })

            validations.append(
                validation_result(
                    "Original / photocopy validation",
                    doc_type,
                    status,
                    f"Original marker: {has_original} | Copy marker: {has_copy} | Score: {score}",
                    severity,
                )
            )

        # 7. Financial validation
        bill_text = extracted_text_by_doc.get("FINAL_HOSPITAL_BILL", "")

        total_bill = extract_money_value(bill_text, "Total Bill Amount")
        insurance_payable = extract_money_value(bill_text, "Insurance Payable")
        patient_copay = extract_money_value(bill_text, "Patient Co-Pay")

        financial_pass = (
                total_bill is not None
                and insurance_payable is not None
                and patient_copay is not None
                and total_bill == insurance_payable + patient_copay
        )

        validations.append(
            validation_result(
                "Financial responsibility split",
                "FINAL_HOSPITAL_BILL",
                "PASS" if financial_pass else "FAIL",
                f"Total: {total_bill} | Insurance: {insurance_payable} | Patient Co-Pay: {patient_copay}",
                "CRITICAL",
            )
        )

        fail_count = len([v for v in validations if v["status"] == "FAIL"])
        warning_count = len([v for v in validations if v["status"] == "WARNING"])

        readiness = 100

        readiness -= fail_count * 20
        readiness -= warning_count * 7

        readiness = max(0, min(100, readiness))

        if fail_count > 0:
            overall_status = "BLOCKED"
        elif warning_count > 0:
            overall_status = "READY_WITH_WARNINGS"
        else:
            overall_status = "READY"

        return {
            "success": True,
            "source": "SEGREGATED_DOCUMENT_VALIDATION",
            "result": {
                "claimId": claim_id,
                "folder": str(folder),
                "checklist": checklist,
                "validations": validations,
                "originalityResults": originality_results,
                "summary": {
                    "readinessPercent": readiness,
                    "overallStatus": overall_status,
                    "failCount": fail_count,
                    "warningCount": warning_count,
                    "criticalIssues": [
                        v for v in validations if v["status"] == "FAIL"
                    ],
                    "warnings": [
                        v for v in validations if v["status"] == "WARNING"
                    ],
                },
            },
        }

    except Exception as e:
        return {
            "success": False,
            "source": "SEGREGATED_DOCUMENT_VALIDATION",
            "error": str(e),
        }


def validation_result(name, document_type, status, evidence, severity="INFO"):
    return {
        "validation": name,
        "documentType": document_type,
        "status": status,
        "severity": severity,
        "evidence": evidence,
    }


def extract_money_value(text: str, label: str):
    pattern = rf"{label}\s*[:\-]?\s*Rs\.?\s*([0-9,]+)"
    match = re.search(pattern, text, re.IGNORECASE)

    if not match:
        return None

    return int(match.group(1).replace(",", ""))


def contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def read_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    text = ""

    for page in reader.pages:
        text += "\n" + (page.extract_text() or "")

    return text


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

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        detected_docs = manifest.get("documentsDetected", [])
        grouped_docs = manifest.get("groupedDocuments", [])

        validation_rows = []
        missing_required = 0
        available_required = 0

        for rule in DISPATCH_CHECKLIST_RULES:
            matched_group_files = [
                doc.get("outputFile")
                for doc in grouped_docs
                if doc.get("groupCode") in rule.get("groupCodes", [])
            ]

            matched_page_files = [
                doc.get("outputFile")
                for doc in detected_docs
                if doc.get("documentType") in rule["documentTypes"]
            ]

            matched_files = matched_group_files or matched_page_files
            matched_files = [f for f in matched_files if f]

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
                status = "MISSING" if rule["required"] else "NOT_AVAILABLE"
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
                "expectedDocumentTypes": rule["documentTypes"],
                "groupCodes": rule.get("groupCodes", []),
                "status": status,
                "matchedFiles": matched_files,
                "matchCount": len(matched_files),
                "remarks": remarks,
            })

        review_required_pages = [
            {
                "pageNumber": doc.get("pageNumber"),
                "outputFile": doc.get("outputFile"),
                "documentType": doc.get("documentType"),
                "reason": doc.get("reason", ""),
                "confidence": doc.get("confidence"),
            }
            for doc in detected_docs
            if doc.get("reviewRequired") or doc.get("documentType") == "UNKNOWN"
        ]

        total_required = len([r for r in DISPATCH_CHECKLIST_RULES if r["required"]])
        readiness_percent = round((available_required / total_required) * 100)

        overall_status = (
            "READY"
            if missing_required == 0 and len(review_required_pages) == 0
            else "REVIEW_REQUIRED"
        )

        result = {
            "claimId": manifest.get("claimId"),
            "patientName": manifest.get("patientName"),
            "patientFolder": manifest.get("patientFolder"),
            "sourceManifest": str(manifest_path),
            "summary": {
                "totalChecklistItems": len(DISPATCH_CHECKLIST_RULES),
                "totalRequired": total_required,
                "availableRequired": available_required,
                "missingRequired": missing_required,
                "reviewRequiredPages": len(review_required_pages),
                "readinessPercent": readiness_percent,
                "overallStatus": overall_status,
            },
            "checklistValidation": validation_rows,
            "reviewRequiredPages": review_required_pages,
            "groupedDocuments": grouped_docs,
        }

        validation_output_path = manifest_path.parent / "dispatch_checklist_validation.json"

        with open(validation_output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        return {
            "success": True,
            "source": "DISPATCH_CHECKLIST_VALIDATION",
            "result": result,
        }

    except Exception as e:
        return {
            "success": False,
            "source": "DISPATCH_CHECKLIST_VALIDATION",
            "error": str(e),
        }


def _read_json_file(path: Path) -> dict[str, Any]:
    """
    Read and validate a JSON object from disk.
    """

    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON file: {path}"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            f"Expected JSON object in file: {path}"
        )

    return payload


CHECKLIST_REVIEW_FILE_NAME = "checklist_review.json"


def _checklist_item_id(
    item_no: str | int,
) -> str:
    """
    Convert checklist item number to a stable API identifier.

    Examples:
        1  -> CHK-001
        14 -> CHK-014
    """
    cleaned = str(item_no or "").strip()

    if not cleaned:
        raise ValueError(
            "Checklist item number is required"
        )

    if cleaned.isdigit():
        return f"CHK-{int(cleaned):03d}"

    safe_value = re.sub(
        r"[^A-Z0-9]+",
        "-",
        cleaned.upper(),
    ).strip("-")

    return f"CHK-{safe_value}"


def _requirement_type_from_validation_row(
    row: dict,
) -> str:
    """
    Preserve future requirementType values while supporting
    the current required: true/false structure.
    """
    explicit_type = str(
        row.get("requirementType") or ""
    ).strip().upper()

    if explicit_type in {
        "REQUIRED",
        "OPTIONAL",
        "CONDITIONAL",
    }:
        return explicit_type

    return (
        "REQUIRED"
        if bool(row.get("required"))
        else "OPTIONAL"
    )


def _system_status_from_validation_row(
    row: dict,
) -> str:
    available = bool(
        row.get("matchedFiles")
        or row.get("available")
        or str(
            row.get("status") or ""
        ).upper() == "AVAILABLE"
    )

    return "PRESENT" if available else "MISSING"


def _default_reviewer_disposition(
    system_status: str,
) -> str:
    if system_status == "PRESENT":
        return "ACCEPTED_PRESENT"

    return "PENDING"


def _reviewer_disposition_from_decision(
    reviewer_decision: str,
) -> str:
    decision_map = {
        "REQUIRED": "REQUIRED_DOCUMENT_NEEDED",
        "OPTIONAL": "OPTIONAL_MISSING_ACCEPTED",
        "NOT_APPLICABLE": "NOT_APPLICABLE",
    }

    try:
        return decision_map[reviewer_decision]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported reviewer decision: "
            f"{reviewer_decision}"
        ) from exc


def _is_checklist_item_resolved(
    system_status: str,
    reviewer_disposition: str,
) -> bool:
    if system_status == "PRESENT":
        return True

    return reviewer_disposition in {
        "OPTIONAL_MISSING_ACCEPTED",
        "NOT_APPLICABLE",
        "UPLOAD_PROVIDED",
        "REQUIRED_MISSING_OVERRIDE",
    }


def _resolve_checklist_review_path(
    claim_id: str,
) -> Path:
    """
    Store reviewer state alongside the claim-pack manifest.

    The original system validation remains separate.
    """
    manifest_path = _resolve_review_manifest_path(
        claim_id
    )

    return (
        manifest_path.parent
        / CHECKLIST_REVIEW_FILE_NAME
    )


def _build_initial_checklist_review(
    claim_id: str,
) -> dict:
    """
    Run the existing checklist validation and convert its output
    into reviewer-editable state.
    """
    validation_response = (
        validate_against_dispatch_checklist(
            claim_id=claim_id
        )
    )

    if not validation_response.get("success"):
        raise ValueError(
            validation_response.get("error")
            or "Checklist validation failed"
        )

    validation_result = (
        validation_response.get("result") or {}
    )

    validation_rows = validation_result.get(
        "checklistValidation",
        [],
    )

    if not isinstance(validation_rows, list):
        validation_rows = []

    review_items: list[dict[str, Any]] = []

    for row in validation_rows:
        if not isinstance(row, dict):
            continue

        item_no = str(
            row.get("itemNo") or ""
        ).strip()

        checklist_item_id = _checklist_item_id(
            item_no
        )

        system_status = (
            _system_status_from_validation_row(row)
        )

        reviewer_disposition = (
            _default_reviewer_disposition(
                system_status
            )
        )

        expected_document_types = row.get(
            "expectedDocumentTypes",
            [],
        )

        if not isinstance(
            expected_document_types,
            list,
        ):
            expected_document_types = []

        matched_files = row.get(
            "matchedFiles",
            [],
        )

        if not isinstance(matched_files, list):
            matched_files = []

        review_items.append({
            "checklistItemId": checklist_item_id,
            "itemNo": item_no,
            "checklistItem": row.get(
                "checklistItem"
            ),
            "requirementType": (
                _requirement_type_from_validation_row(
                    row
                )
            ),
            "expectedDocumentTypes": (
                expected_document_types
            ),
            "systemStatus": system_status,
            "reviewerDecision": (
                "REQUIRED"
                if bool(row.get("required"))
                else "OPTIONAL"
            ),
            "reviewerDisposition": (
                reviewer_disposition
            ),
            "reviewerRemarks": "",
            "resolved": (
                _is_checklist_item_resolved(
                    system_status=system_status,
                    reviewer_disposition=(
                        reviewer_disposition
                    ),
                )
            ),
            "matchedFiles": matched_files,
            "uploadedDocumentIds": [],
            "updatedAt": None,
        })

    review_document = {
        "claimId": (
            validation_result.get("claimId")
            or claim_id
        ),
        "patientName": validation_result.get(
            "patientName"
        ),
        "patientFolder": validation_result.get(
            "patientFolder"
        ),
        "reviewStatus": "IN_PROGRESS",
        "createdAt": datetime.now().isoformat(),
        "updatedAt": datetime.now().isoformat(),
        "items": review_items,
    }

    _recalculate_checklist_review_summary(
        review_document
    )

    return review_document


def _recalculate_checklist_review_summary(
    review_document: dict,
) -> None:
    items = review_document.get("items", [])

    if not isinstance(items, list):
        items = []

    total_items = len(items)

    present_items = sum(
        1
        for item in items
        if item.get("systemStatus") == "PRESENT"
    )

    missing_items = sum(
        1
        for item in items
        if item.get("systemStatus") == "MISSING"
    )

    resolved_items = sum(
        1
        for item in items
        if bool(item.get("resolved"))
    )

    unresolved_items = (
        total_items - resolved_items
    )

    missing_required = sum(
        1
        for item in items
        if (
            item.get("systemStatus") == "MISSING"
            and item.get("reviewerDisposition")
            == "REQUIRED_DOCUMENT_NEEDED"
        )
    )

    review_document["summary"] = {
        "totalItems": total_items,
        "presentItems": present_items,
        "missingItems": missing_items,
        "resolvedItems": resolved_items,
        "unresolvedItems": unresolved_items,
        "missingRequiredDocuments": (
            missing_required
        ),
        "allItemsResolved": (
            unresolved_items == 0
        ),
    }

    review_document["reviewStatus"] = (
        "RESOLVED"
        if unresolved_items == 0
        else "IN_PROGRESS"
    )

    review_document["updatedAt"] = (
        datetime.now().isoformat()
    )


def _write_checklist_review(
    path: Path,
    review_document: dict,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = path.with_suffix(
        ".json.tmp"
    )

    with temp_path.open(
        "w",
        encoding="utf-8",
    ) as review_file:
        json.dump(
            review_document,
            review_file,
            indent=2,
            ensure_ascii=False,
        )

    temp_path.replace(path)


def get_or_create_checklist_review(
    claim_id: str,
) -> tuple[Path, dict]:
    clean_claim_id = str(
        claim_id or ""
    ).strip()

    if not clean_claim_id:
        raise ValueError(
            "claim_id is required"
        )

    review_path = (
        _resolve_checklist_review_path(
            clean_claim_id
        )
    )

    if review_path.exists():
        return (
            review_path,
            _read_json_file(review_path),
        )

    review_document = (
        _build_initial_checklist_review(
            clean_claim_id
        )
    )

    _write_checklist_review(
        path=review_path,
        review_document=review_document,
    )

    return review_path, review_document


def get_claim_packet_checklist_review(
    claim_id: str,
) -> dict[str, Any]:
    """
    Retrieve the checklist review JSON document for a given claim ID.
    Reads from checklist_review.json or generates initial review state.
    """
    clean_claim_id = str(
        claim_id or ""
    ).strip()

    if not clean_claim_id:
        raise ValueError(
            "claim_id is required"
        )

    review_path, review_document = (
        get_or_create_checklist_review(
            clean_claim_id
        )
    )

    return {
        "success": True,
        "source": "CLAIM_PACKET_CHECKLIST_REVIEW",
        "result": review_document,
    }


def get_claim_packet_checklist_item_detail(
    claim_id: str,
    checklist_item_id: str,
) -> dict[str, Any]:
    """
    Retrieve specific checklist item details (including checklistItemId) for a claim ID.
    """
    clean_claim_id = str(
        claim_id or ""
    ).strip()

    clean_item_id = str(
        checklist_item_id or ""
    ).strip().upper()

    if not clean_claim_id:
        raise ValueError(
            "claim_id is required"
        )

    if not clean_item_id:
        raise ValueError(
            "checklist_item_id is required"
        )

    review_path, review_document = (
        get_or_create_checklist_review(
            clean_claim_id
        )
    )

    items = review_document.get("items", [])
    if not isinstance(items, list):
        items = []

    target_chk_id = (
        _checklist_item_id(clean_item_id)
        if clean_item_id.isdigit()
        else clean_item_id
    )

    selected_item = next(
        (
            item
            for item in items
            if str(
                item.get("checklistItemId") or ""
            ).upper() in (clean_item_id, target_chk_id)
            or str(
                item.get("itemNo") or ""
            ).upper() == clean_item_id
        ),
        None,
    )

    if selected_item is None:
        raise FileNotFoundError(
            f"Checklist item not found: {clean_item_id}"
        )

    return {
        "success": True,
        "source": "CLAIM_PACKET_CHECKLIST_ITEM_DETAIL",
        "result": selected_item,
    }


def _safe_int(value: Any) -> int | None:
    """
    Convert manifest values to int without raising errors.
    """

    if value is None or value == "":
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def update_claim_packet_checklist_item(
    claim_id: str,
    checklist_item_id: str,
    payload: dict,
) -> dict[str, Any]:
    try:
        clean_claim_id = str(
            claim_id or ""
        ).strip()

        clean_item_id = str(
            checklist_item_id or ""
        ).strip().upper()

        if not clean_claim_id:
            raise ValueError(
                "claim_id is required"
            )

        if not clean_item_id:
            raise ValueError(
                "checklist_item_id is required"
            )

        reviewer_decision = str(
            payload.get("reviewerDecision")
            or ""
        ).strip().upper()

        reviewer_remarks = str(
            payload.get("reviewerRemarks")
            or ""
        ).strip()

        review_path, review_document = (
            get_or_create_checklist_review(
                clean_claim_id
            )
        )

        items = review_document.get(
            "items",
            [],
        )

        target_chk_id = _checklist_item_id(clean_item_id) if clean_item_id.isdigit() else clean_item_id

        selected_item = next(
            (
                item
                for item in items
                if str(
                    item.get("checklistItemId")
                    or ""
                ).upper() in (clean_item_id, target_chk_id)
                or str(
                    item.get("itemNo")
                    or ""
                ).upper() == clean_item_id
            ),
            None,
        )

        if selected_item is None:
            raise FileNotFoundError(
                "Checklist item not found: "
                f"{clean_item_id}"
            )

        system_status = str(
            selected_item.get("systemStatus")
            or ""
        ).upper()

        if system_status == "PRESENT":
            raise ValueError(
                "Reviewer decision can only be "
                "changed for a missing document"
            )

        reviewer_disposition = (
            _reviewer_disposition_from_decision(
                reviewer_decision
            )
        )

        selected_item["reviewerDecision"] = (
            reviewer_decision
        )
        selected_item["reviewerDisposition"] = (
            reviewer_disposition
        )
        selected_item["reviewerRemarks"] = (
            reviewer_remarks
        )
        selected_item["resolved"] = (
            _is_checklist_item_resolved(
                system_status=system_status,
                reviewer_disposition=(
                    reviewer_disposition
                ),
            )
        )
        selected_item["updatedAt"] = (
            datetime.now().isoformat()
        )

        previous_decision = selected_item.get(
            "reviewerDecision"
        )

        previous_disposition = selected_item.get(
            "reviewerDisposition"
        )

        _recalculate_checklist_review_summary(
            review_document
        )

        _write_checklist_review(
            path=review_path,
            review_document=review_document,
        )

        persisted_review = _read_json_file(
            review_path
        )

        persisted_item = next(
            (
                item
                for item in persisted_review.get(
                "items",
                [],
            )
                if str(
                item.get("checklistItemId")
                or ""
            ).upper() == clean_item_id
            ),
            None,
        )

        if persisted_item is None:
            raise RuntimeError(
                "Checklist item was not found after save"
            )

        return {
            "success": True,
            "source": "CHECKLIST_ITEM_REVIEW",
            "result": {
                "claimId": clean_claim_id,
                "checklistReviewPath": str(
                    review_path
                ),
                "previousDecision": previous_decision,
                "previousDisposition": (
                    previous_disposition
                ),
                "reviewStatus": (
                    persisted_review.get(
                        "reviewStatus"
                    )
                ),
                "summary": persisted_review.get(
                    "summary"
                ),
                "item": persisted_item,
            },
        }

    except FileNotFoundError as exc:
        return {
            "success": False,
            "source": "CHECKLIST_ITEM_REVIEW",
            "errorCode": "NOT_FOUND",
            "error": str(exc),
        }

    except ValueError as exc:
        return {
            "success": False,
            "source": "CHECKLIST_ITEM_REVIEW",
            "errorCode": "VALIDATION_ERROR",
            "error": str(exc),
        }

    except Exception as exc:
        logger.exception(
            "Failed to update checklist item: "
            "claim_id=%s checklist_item_id=%s",
            claim_id,
            checklist_item_id,
        )

        return {
            "success": False,
            "source": "CHECKLIST_ITEM_REVIEW",
            "errorCode": "INTERNAL_ERROR",
            "error": str(exc),
        }


def _safe_float(value: Any) -> float:
    """
    Convert manifest confidence values safely.
    """

    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _normalise_candidate_types(
    candidates: Any,
) -> list[dict[str, Any]]:
    """
    Return candidate document types in a consistent format.
    """

    if not isinstance(candidates, list):
        return []

    normalised: list[dict[str, Any]] = []

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        document_type = str(
            candidate.get("type")
            or candidate.get("documentType")
            or ""
        ).strip()

        if not document_type:
            continue

        normalised.append(
            {
                "type": document_type,
                "confidence": _safe_float(
                    candidate.get("confidence")
                ),
            }
        )

    normalised.sort(
        key=lambda item: item["confidence"],
        reverse=True,
    )

    return normalised


def _build_review_page(
    page: dict[str, Any],
    group_id: str | None,
) -> dict[str, Any]:
    """
    Convert one documentsDetected entry into the UI review DTO.
    """

    page_number = _safe_int(
        page.get("pageNumber")
    )

    raw_document_type = str(
        page.get("rawDocumentType")
        or page.get("documentType")
        or "UNKNOWN"
    )

    final_document_type = str(
        page.get("documentType")
        or raw_document_type
        or "UNKNOWN"
    )

    identifiers = {
        "patientName": page.get("patientName") or "",
        "claimNumber": page.get("claimNumber") or "",
        "mrn": page.get("mrn") or "",
        "ipNumber": page.get("ipNumber") or "",
        "payerName": page.get("payerName") or "",
        "billNumber": page.get("billNumber") or "",
        "authorizationNumber": (
            page.get("authorizationNumber") or ""
        ),
        "policyNumber": page.get("policyNumber") or "",
        "memberId": page.get("memberId") or "",
    }

    financial_metadata = {
        "documentDate": page.get("documentDate") or "",
        "totalAmount": page.get("totalAmount") or "",
    }

    return {
        "pageId": (
            f"page-{page_number}"
            if page_number is not None
            else None
        ),
        "pageNumber": page_number,
        "sourcePageNumber": page_number,
        "groupId": group_id,
        "documentType": final_document_type,
        "finalDocumentType": final_document_type,
        "rawDocumentType": raw_document_type,
        "documentFamily": (
            page.get("documentFamily") or ""
        ),
        "visibleTitle": page.get("visibleTitle") or "",
        "sectionTitle": page.get("sectionTitle") or "",
        "pageRole": page.get("pageRole") or "UNKNOWN",
        "printedPageNumber": _safe_int(
            page.get("printedPageNumber")
        ),
        "printedTotalPages": _safe_int(
            page.get("printedTotalPages")
        ),
        "explicitDocumentStart": bool(
            page.get("explicitDocumentStart")
        ),
        "explicitDocumentEnd": bool(
            page.get("explicitDocumentEnd")
        ),
        "standaloneDocument": bool(
            page.get("standaloneDocument")
        ),
        "templateHint": page.get("templateHint") or "",
        "headerSignature": (
            page.get("headerSignature") or ""
        ),
        "footerSignature": (
            page.get("footerSignature") or ""
        ),
        "continuationIndicators": (
            page.get("continuationIndicators")
            if isinstance(
                page.get("continuationIndicators"),
                list,
            )
            else []
        ),
        "confidence": _safe_float(
            page.get("confidence")
        ),
        "classificationSource": (
            page.get("source")
            or page.get("classificationSource")
            or ""
        ),
        "reason": page.get("reason") or "",
        "reviewRequired": bool(
            page.get("reviewRequired")
        ),
        "reviewReason": (
            page.get("reviewReason")
            or page.get("reason")
            or ""
            if page.get("reviewRequired")
            else ""
        ),
        "candidateDocumentTypes": (
            _normalise_candidate_types(
                page.get("candidateDocumentTypes")
            )
        ),
        "identifiers": identifiers,
        "financialMetadata": financial_metadata,
        "outputFile": page.get("outputFile") or "",
    }


def _group_source_pages(
    group: dict[str, Any],
) -> list[int]:
    """
    Support both sourcePages and pageNumbers naming.
    """

    raw_pages = (
        group.get("sourcePages")
        or group.get("pageNumbers")
        or []
    )

    if not isinstance(raw_pages, list):
        return []

    pages: list[int] = []

    for value in raw_pages:
        page_number = _safe_int(value)

        if page_number is not None:
            pages.append(page_number)

    return pages


def _resolve_review_manifest_path(
    claim_id: str,
) -> Path:
    """
    Resolve the most appropriate manifest for document review.

    Priority:
    1. Find the claim-pack manifest whose claimId matches.
    2. Fall back to the segregated claim manifest.
    """

    # First try the segregated manifest only to identify
    # patientFolder / claimPackFolder.
    segregated_manifest_path = (
        CLAIM_PACKET_SEGREGATED_DIR
        / claim_id
        / "manifest.json"
    )

    if segregated_manifest_path.exists():
        segregated_manifest = _read_json_file(
            segregated_manifest_path
        )

        patient_folder = str(
            segregated_manifest.get("patientFolder")
            or ""
        ).strip()

        if patient_folder:
            claim_pack_manifest_path = (
                CLAIM_PACKET_GROUPED_DIR
                / patient_folder
                / "manifest.json"
            )

            if claim_pack_manifest_path.exists():
                return claim_pack_manifest_path

        claim_pack_folder = str(
            segregated_manifest.get("claimPackFolder")
            or ""
        ).strip()

        if claim_pack_folder:
            claim_pack_manifest_path = (
                Path(claim_pack_folder)
                / "manifest.json"
            )

            if claim_pack_manifest_path.exists():
                return claim_pack_manifest_path

    # Fallback for older packets or incomplete claim-pack output.
    if segregated_manifest_path.exists():
        return segregated_manifest_path

    raise FileNotFoundError(
        f"No review manifest found for claim_id={claim_id}"
    )

def get_claim_packet_review(
    claim_id: str,
) -> dict[str, Any]:
    """
    Build the MVP Document Review Workspace response.

    Reads the existing claim manifest and combines:
    - document groups
    - source pages
    - classification metadata
    - AI review warnings
    """

    clean_claim_id = str(claim_id or "").strip()

    if not clean_claim_id:
        return {
            "success": False,
            "source": "CLAIM_PACKET_REVIEW",
            "error": "claim_id is required",
        }

    manifest_path = _resolve_review_manifest_path(
        clean_claim_id
    )

    try:
        manifest = _read_json_file(manifest_path)

        detected_pages = manifest.get(
            "documentsDetected",
            [],
        )

        grouped_documents = manifest.get(
            "groupedDocuments",
            [],
        )

        if not isinstance(detected_pages, list):
            detected_pages = []

        if not isinstance(grouped_documents, list):
            grouped_documents = []

        # Fast lookup of page metadata by source page number.
        page_lookup: dict[int, dict[str, Any]] = {}

        for page in detected_pages:
            if not isinstance(page, dict):
                continue

            page_number = _safe_int(
                page.get("pageNumber")
            )

            if page_number is not None:
                page_lookup[page_number] = page

        review_groups: list[dict[str, Any]] = []
        assigned_page_numbers: set[int] = set()

        for sequence, group in enumerate(
            grouped_documents,
            start=1,
        ):
            if not isinstance(group, dict):
                continue

            group_id = str(
                group.get("groupId")
                or group.get("group_id")
                or f"{clean_claim_id}-group-{sequence:03d}"
            )

            source_pages = _group_source_pages(group)

            group_pages: list[dict[str, Any]] = []

            for position, page_number in enumerate(
                source_pages,
                start=1,
            ):
                page_data = page_lookup.get(
                    page_number,
                    {
                        "pageNumber": page_number,
                        "documentType": (
                            group.get("documentType")
                            or "UNKNOWN"
                        ),
                        "confidence": (
                            group.get("confidence")
                            or 0
                        ),
                    },
                )

                review_page = _build_review_page(
                    page=page_data,
                    group_id=group_id,
                )

                review_page["positionInGroup"] = position
                group_pages.append(review_page)
                assigned_page_numbers.add(page_number)

            status = str(
                group.get("status") or "RESOLVED"
            ).upper()

            review_flags = group.get(
                "reviewFlags",
                [],
            )

            if not isinstance(review_flags, list):
                review_flags = [str(review_flags)]

            review_required = (
                status == "REVIEW"
                or bool(review_flags)
                or any(
                    page.get("reviewRequired")
                    for page in group_pages
                )
            )

            document_type = str(
                group.get("documentType")
                or group.get("document_type")
                or "UNKNOWN"
            )

            display_name = str(
                group.get("displayName")
                or group.get("documentName")
                or document_type.replace("_", " ").title()
            )

            review_groups.append(
                {
                    "groupId": group_id,
                    "sequence": sequence,
                    "documentType": document_type,
                    "displayName": display_name,
                    "documentFamily": (
                        group.get("documentFamily")
                        or group.get("family")
                        or group.get("document_family")
                        or ""
                    ),
                    "groupCode": (
                        group.get("groupCode") or ""
                    ),
                    "sourcePages": source_pages,
                    "pageCount": len(source_pages),
                    "confidence": _safe_float(
                        group.get("confidence")
                    ),
                    "status": status,
                    "reviewRequired": review_required,
                    "reviewFlags": review_flags,
                    "reviewed": False,
                    "reviewerRemarks": "",
                    "outputFile": (
                        group.get("outputFile")
                        or group.get("output_file_name")
                        or ""
                    ),
                    "pages": group_pages,
                }
            )

        # Any detected page that is not present in a group is returned
        # under unassignedPages instead of being silently lost.
        unassigned_pages: list[dict[str, Any]] = []

        for page_number in sorted(page_lookup):
            if page_number in assigned_page_numbers:
                continue

            unassigned_pages.append(
                _build_review_page(
                    page=page_lookup[page_number],
                    group_id=None,
                )
            )

        total_pages = _safe_int(
            manifest.get("totalPages")
        ) or len(detected_pages)

        review_required_groups = sum(
            1
            for group in review_groups
            if group["reviewRequired"]
        )

        review_required_pages = sum(
            1
            for page in detected_pages
            if isinstance(page, dict)
            and page.get("reviewRequired")
        )

        all_grouped_pages = [
            page_number
            for group in review_groups
            for page_number in group["sourcePages"]
        ]

        duplicate_page_numbers = sorted(
            {
                page_number
                for page_number in all_grouped_pages
                if all_grouped_pages.count(page_number) > 1
            }
        )

        integrity_valid = (
            not unassigned_pages
            and not duplicate_page_numbers
            and len(set(all_grouped_pages)) == total_pages
        )

        supplemental_documents = (
            _load_supplemental_documents(
                clean_claim_id
            )
        )

        return {
            "success": True,
            "source": "CLAIM_PACKET_REVIEW",
            "result": {
                "claimId": manifest.get(
                    "claimId",
                    clean_claim_id,
                ),
                "packetId": manifest.get(
                    "packetId",
                    clean_claim_id,
                ),
                "patientName": (
                    manifest.get("patientName")
                    or "Unknown Patient"
                ),
                "patientFolder": (
                    manifest.get("patientFolder") or ""
                ),
                "status": (
                    "REVIEW_REQUIRED"
                    if (
                        review_required_groups > 0
                        or review_required_pages > 0
                        or unassigned_pages
                    )
                    else "READY_FOR_VALIDATION"
                ),
                "source": {
                    "sourceFile": (
                        manifest.get("sourceFile") or ""
                    ),
                    "totalPages": total_pages,
                },
                "uploadedDocuments": (
                    supplemental_documents
                ),
                "summary": {
                    "totalPages": total_pages,
                    "documentGroupCount": len(
                        review_groups
                    ),
                    "reviewRequiredGroupCount": (
                        review_required_groups
                    ),
                    "reviewRequiredPageCount": (
                        review_required_pages
                    ),
                    "unassignedPageCount": len(
                        unassigned_pages
                    ),
                    "duplicatePageCount": len(
                        duplicate_page_numbers
                    ),
                    "duplicatePageNumbers": (
                        duplicate_page_numbers
                    ),
                    "pageIntegrityValid": integrity_valid,
                    "logicalGroupingIntegrityValid": (
                        manifest.get(
                            "logicalGroupingIntegrityValid",
                            integrity_valid,
                        )
                    ),
                    "physicalGroupingIntegrityValid": (
                        manifest.get(
                            "physicalGroupingIntegrityValid",
                            integrity_valid,
                        )
                    ),

                    "uploadedDocumentCount": len(
                        supplemental_documents
                    ),
                    "unassignedUploadedDocumentCount": sum(
                        1
                        for document in supplemental_documents
                        if document.get("assignmentStatus")
                        == "UNASSIGNED"
                    ),
                },
                "groups": review_groups,
                "unassignedPages": unassigned_pages,
                "checklistStatus": manifest.get(
                    "checklistStatus",
                    [],
                ),
                "manifestPath": str(manifest_path),
            },
        }

    except FileNotFoundError:
        return {
            "success": False,
            "source": "CLAIM_PACKET_REVIEW",
            "error": (
                "Claim packet manifest not found for "
                f"claim_id={clean_claim_id}"
            ),
            "manifestPath": str(manifest_path),
        }

    except Exception as exc:
        print(
            "CLAIM PACKET REVIEW ERROR:",
            repr(exc),
        )

        return {
            "success": False,
            "source": "CLAIM_PACKET_REVIEW",
            "error": str(exc),
        }


def normalize_evidence_text(value: str | None) -> str:
    if not value:
        return ""

    return re.sub(
        r"[^A-Z0-9]",
        "",
        str(value).upper(),
    )


def identifier_exists_in_text(
    value: str | None,
    page_text: str | None,
) -> bool:
    """
    Confirm that an extracted identifier occurs in PDF text.

    This works for text-based PDFs. Scanned pages need a separate
    evidence-verification method.
    """

    normalized_value = normalize_evidence_text(value)
    normalized_text = normalize_evidence_text(page_text)

    if not normalized_value:
        return False

    if not normalized_text:
        return False

    return normalized_value in normalized_text


def resolve_claim_packet_manifest(
    claim_id: str,
) -> tuple[Path, dict]:
    clean_claim_id = str(claim_id or "").strip()

    if not clean_claim_id:
        raise ValueError("claim_id is required")

    manifest_path = (
        CLAIM_PACKET_SEGREGATED_DIR
        / clean_claim_id
        / "manifest.json"
    )

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Claim packet manifest not found: {manifest_path}"
        )

    manifest = _read_json_file(manifest_path)

    return manifest_path, manifest


def resolve_claim_packet_source_pdf(
    claim_id: str,
) -> tuple[Path, dict]:
    _, manifest = resolve_claim_packet_manifest(
        claim_id
    )

    source_file = str(
        manifest.get("sourceFile") or ""
    ).strip()

    if not source_file:
        raise ValueError(
            "sourceFile is missing from claim manifest"
        )

    source_pdf_path = Path(source_file)

    if not source_pdf_path.exists():
        raise FileNotFoundError(
            f"Source PDF not found: {source_pdf_path}"
        )

    return source_pdf_path, manifest


def validate_review_page_arrangement(
    total_pages: int,
    groups: list[dict],
    unassigned_page_numbers: list[int] | None = None,
) -> dict:
    expected_pages = set(
        range(1, total_pages + 1)
    )

    submitted_pages: list[int] = []

    for group in groups:
        page_numbers = group.get(
            "pageNumbers",
            [],
        )

        if not isinstance(page_numbers, list):
            raise ValueError(
                "Every group must contain a pageNumbers list"
            )

        submitted_pages.extend(page_numbers)

    unassigned_pages = list(
        unassigned_page_numbers or []
    )

    submitted_pages.extend(unassigned_pages)

    submitted_set = set(submitted_pages)

    duplicate_pages = sorted({
        page_number
        for page_number in submitted_pages
        if submitted_pages.count(page_number) > 1
    })

    missing_pages = sorted(
        expected_pages - submitted_set
    )

    invalid_pages = sorted(
        submitted_set - expected_pages
    )

    return {
        "valid": (
            not duplicate_pages
            and not missing_pages
            and not invalid_pages
            and not unassigned_pages
        ),
        "expectedPageCount": total_pages,
        "submittedPageCount": len(submitted_pages),
        "uniqueSubmittedPageCount": len(submitted_set),
        "missingPageNumbers": missing_pages,
        "duplicatePageNumbers": duplicate_pages,
        "invalidPageNumbers": invalid_pages,
        "unassignedPageNumbers": sorted(
            set(unassigned_pages)
        ),
    }


def reviewed_output_file_name(
    sequence: int,
    document_type: str,
) -> str:
    safe_type = re.sub(
        r"[^A-Z0-9_]+",
        "_",
        str(document_type or "UNKNOWN").upper(),
    ).strip("_")

    if not safe_type:
        safe_type = "UNKNOWN"

    return f"{sequence:03d}_{safe_type}.pdf"


def save_and_regenerate_claim_packet_review(
    claim_id: str,
    payload: dict,
) -> dict:
    try:
        source_pdf_path, ai_manifest = (
            resolve_claim_packet_source_pdf(
                claim_id
            )
        )

        groups = payload.get("groups") or []
        unassigned_pages = payload.get(
            "unassignedPageNumbers"
        ) or []

        if not groups:
            return {
                "success": False,
                "source": "CLAIM_PACKET_REVIEW_SAVE",
                "error": (
                    "At least one reviewed document group "
                    "is required"
                ),
            }

        reader = PdfReader(
            str(source_pdf_path)
        )
        total_pages = len(reader.pages)

        integrity = validate_review_page_arrangement(
            total_pages=total_pages,
            groups=groups,
            unassigned_page_numbers=unassigned_pages,
        )

        if not integrity["valid"]:
            return {
                "success": False,
                "source": "CLAIM_PACKET_REVIEW_SAVE",
                "error": "Invalid reviewed page arrangement",
                "integrity": integrity,
            }

        patient_folder = str(
            ai_manifest.get("patientFolder")
            or "unknown-patient"
        ).strip()

        reviewed_root = (
            CLAIM_PACKET_GROUPED_DIR
            / patient_folder
            / claim_id
            / "reviewed"
        )

        temp_output_dir = (
            reviewed_root.parent
            / f".reviewed-{uuid4().hex}"
        )

        temp_output_dir.mkdir(
            parents=True,
            exist_ok=False,
        )

        reviewed_documents: list[dict] = []

        try:
            for sequence, group in enumerate(
                groups,
                start=1,
            ):
                document_type = str(
                    group.get("documentType")
                    or "UNKNOWN"
                ).strip().upper()

                page_numbers = [
                    int(page_number)
                    for page_number
                    in group.get("pageNumbers", [])
                ]

                output_file = (
                    reviewed_output_file_name(
                        sequence=sequence,
                        document_type=document_type,
                    )
                )

                output_path = (
                    temp_output_dir
                    / output_file
                )

                write_merged_pdf(
                    reader=reader,
                    page_numbers=page_numbers,
                    output_path=output_path,
                )

                group_id = str(
                    group.get("groupId")
                    or f"{claim_id}-reviewed-{sequence:03d}"
                )

                reviewed_documents.append({
                    "groupId": group_id,
                    "sequence": sequence,
                    "documentType": document_type,
                    "displayName": (
                        group.get("displayName")
                        or document_type.replace(
                            "_",
                            " ",
                        ).title()
                    ),
                    "pageNumbers": page_numbers,
                    "sourcePages": page_numbers,
                    "pageCount": len(page_numbers),
                    "outputFile": output_file,
                    "filePath": str(output_path),
                    "reviewerRemarks": (
                        group.get("reviewerRemarks")
                        or ""
                    ),
                    "status": "REVIEWED",
                })

            reviewed_manifest = {
                "claimId": claim_id,
                "packetId": (
                    ai_manifest.get("packetId")
                    or claim_id
                ),
                "patientName": ai_manifest.get(
                    "patientName"
                ),
                "patientFolder": patient_folder,
                "sourceFile": str(source_pdf_path),
                "sourceManifest": str(
                    CLAIM_PACKET_SEGREGATED_DIR
                    / claim_id
                    / "manifest.json"
                ),
                "reviewStatus": (
                    "CONFIRMED"
                    if payload.get("confirmReview")
                    else "DRAFT"
                ),
                "reviewedAt": datetime.now().isoformat(),
                "reviewerRemarks": (
                    payload.get("reviewerRemarks")
                    or ""
                ),
                "totalPages": total_pages,
                "pageIntegrityValid": True,
                "integrity": integrity,
                "groupedDocuments": reviewed_documents,
            }

            reviewed_manifest_path = (
                temp_output_dir
                / "reviewed_manifest.json"
            )

            with reviewed_manifest_path.open(
                "w",
                encoding="utf-8",
            ) as manifest_file:
                json.dump(
                    reviewed_manifest,
                    manifest_file,
                    indent=2,
                    ensure_ascii=False,
                )

            if reviewed_root.exists():
                shutil.rmtree(reviewed_root)

            temp_output_dir.rename(
                reviewed_root
            )

        except Exception:
            if temp_output_dir.exists():
                shutil.rmtree(
                    temp_output_dir,
                    ignore_errors=True,
                )
            raise

        # Paths were initially built under the temporary directory.
        # Replace them with final reviewed-directory paths.
        for document in reviewed_documents:
            final_path = (
                reviewed_root
                / document["outputFile"]
            )

            document["filePath"] = str(
                final_path
            )
            document["previewUrl"] = (
                f"/api/claim-packets/{claim_id}"
                f"/reviewed-groups/"
                f"{document['groupId']}/preview"
            )

        reviewed_manifest[
            "groupedDocuments"
        ] = reviewed_documents

        final_manifest_path = (
            reviewed_root
            / "reviewed_manifest.json"
        )

        with final_manifest_path.open(
            "w",
            encoding="utf-8",
        ) as manifest_file:
            json.dump(
                reviewed_manifest,
                manifest_file,
                indent=2,
                ensure_ascii=False,
            )

        return {
            "success": True,
            "source": "CLAIM_PACKET_REVIEW_SAVE",
            "result": {
                "claimId": claim_id,
                "reviewStatus": reviewed_manifest[
                    "reviewStatus"
                ],
                "reviewedManifestPath": str(
                    final_manifest_path
                ),
                "integrity": integrity,
                "groups": reviewed_documents,
            },
        }

    except Exception as exc:
        logger.exception(
            "Failed to save claim packet review: claim_id=%s",
            claim_id,
        )

        return {
            "success": False,
            "source": "CLAIM_PACKET_REVIEW_SAVE",
            "error": str(exc),
        }


def resolve_claim_packet_page_preview(
    claim_id: str,
    page_number: int,
) -> Path:
    _, manifest = resolve_claim_packet_manifest(
        claim_id
    )

    documents = manifest.get(
        "documentsDetected",
        [],
    )

    for document in documents:
        if int(
            document.get("pageNumber") or 0
        ) != page_number:
            continue

        candidate_paths = [
            document.get("segregatedFile"),
            (
                CLAIM_PACKET_SEGREGATED_DIR
                / claim_id
                / str(
                    document.get("outputFile")
                    or ""
                )
            ),
        ]

        for candidate in candidate_paths:
            if not candidate:
                continue

            path = Path(candidate)

            if path.exists() and path.is_file():
                return path

    raise FileNotFoundError(
        f"Page preview not found: "
        f"claim_id={claim_id}, page={page_number}"
    )


def resolve_claim_packet_group_preview(
    claim_id: str,
    group_id: str,
) -> Path:
    manifest_path = _resolve_review_manifest_path(
        claim_id
    )
    manifest = _read_json_file(
        manifest_path
    )

    for group in manifest.get(
        "groupedDocuments",
        [],
    ):
        if str(
            group.get("groupId") or ""
        ) != group_id:
            continue

        file_path = str(
            group.get("filePath") or ""
        ).strip()

        if file_path:
            path = Path(file_path)

            if path.exists():
                return path

        output_file = str(
            group.get("outputFile") or ""
        ).strip()

        if output_file:
            candidate = (
                manifest_path.parent
                / output_file
            )

            if candidate.exists():
                return candidate

    raise FileNotFoundError(
        f"Group preview not found: "
        f"claim_id={claim_id}, group_id={group_id}"
    )


def resolve_reviewed_group_preview(
    claim_id: str,
    group_id: str,
) -> Path:
    _, ai_manifest = resolve_claim_packet_manifest(
        claim_id
    )

    patient_folder = str(
        ai_manifest.get("patientFolder")
        or "unknown-patient"
    )

    reviewed_root = (
        CLAIM_PACKET_GROUPED_DIR
        / patient_folder
        / claim_id
        / "reviewed"
    )

    reviewed_manifest_path = (
        reviewed_root
        / "reviewed_manifest.json"
    )

    reviewed_manifest = _read_json_file(
        reviewed_manifest_path
    )

    for group in reviewed_manifest.get(
        "groupedDocuments",
        [],
    ):
        if str(
            group.get("groupId") or ""
        ) != group_id:
            continue

        path = (
            reviewed_root
            / str(group.get("outputFile") or "")
        )

        if path.exists():
            return path

    raise FileNotFoundError(
        f"Reviewed group preview not found: "
        f"claim_id={claim_id}, group_id={group_id}"
    )


def resolve_reviewed_folder_and_manifest(
    claim_id: str,
) -> tuple[Path, Path | None, dict | None]:
    clean_claim_id = str(claim_id or "").strip()

    if not clean_claim_id:
        raise ValueError("claim_id is required")

    reviewed_root: Path | None = None

    segregated_manifest_path = (
        CLAIM_PACKET_SEGREGATED_DIR
        / clean_claim_id
        / "manifest.json"
    )

    if segregated_manifest_path.exists():
        manifest = _read_json_file(segregated_manifest_path)
        patient_folder = str(
            manifest.get("patientFolder") or ""
        ).strip()

        if patient_folder:
            candidate = (
                CLAIM_PACKET_GROUPED_DIR
                / patient_folder
                / clean_claim_id
                / "reviewed"
            )
            if candidate.exists():
                reviewed_root = candidate

    if not reviewed_root:
        candidate = (
            CLAIM_PACKET_SEGREGATED_DIR
            / clean_claim_id
            / "reviewed"
        )
        if candidate.exists():
            reviewed_root = candidate

    if not reviewed_root and CLAIM_PACKET_GROUPED_DIR.exists():
        for subfolder in CLAIM_PACKET_GROUPED_DIR.iterdir():
            if subfolder.is_dir():
                candidate = subfolder / clean_claim_id / "reviewed"
                if candidate.exists():
                    reviewed_root = candidate
                    break

    if not reviewed_root or not reviewed_root.exists():
        raise FileNotFoundError(
            f"No reviewed folder found for claim_id={clean_claim_id}"
        )

    reviewed_manifest_path = (
        reviewed_root / "reviewed_manifest.json"
    )
    reviewed_manifest = None

    if reviewed_manifest_path.exists():
        reviewed_manifest = _read_json_file(
            reviewed_manifest_path
        )

    return (
        reviewed_root,
        reviewed_manifest_path if reviewed_manifest_path.exists() else None,
        reviewed_manifest,
    )


def get_claim_packet_reviewed_list(
    claim_id: str,
) -> dict[str, Any]:
    """
    Build the Reviewed Document List response by reading files
    and manifest under the claim ID /reviewed folder.
    """
    clean_claim_id = str(claim_id or "").strip()

    if not clean_claim_id:
        return {
            "success": False,
            "source": "CLAIM_PACKET_REVIEWED_LIST",
            "error": "claim_id is required",
        }

    reviewed_root, reviewed_manifest_path, reviewed_manifest = (
        resolve_reviewed_folder_and_manifest(clean_claim_id)
    )

    files_in_reviewed_folder: list[dict[str, Any]] = []
    if reviewed_root and reviewed_root.exists():
        for path in sorted(reviewed_root.iterdir()):
            if path.is_file():
                stat = path.stat()
                files_in_reviewed_folder.append({
                    "fileName": path.name,
                    "filePath": str(path),
                    "fileSize": stat.st_size,
                    "modifiedAt": datetime.fromtimestamp(
                        stat.st_mtime
                    ).isoformat(),
                })

    manifest_data = reviewed_manifest or {}
    grouped_documents = manifest_data.get("groupedDocuments", [])
    if isinstance(grouped_documents, list):
        for doc in grouped_documents:
            if isinstance(doc, dict) and "groupId" in doc:
                group_id = doc["groupId"]
                doc["previewUrl"] = (
                    f"/api/claim-packets/{clean_claim_id}"
                    f"/reviewed-groups/{group_id}/preview"
                )

    return {
        "success": True,
        "source": "CLAIM_PACKET_REVIEWED_LIST",
        "result": {
            "claimId": manifest_data.get("claimId", clean_claim_id),
            "packetId": manifest_data.get("packetId", clean_claim_id),
            "patientName": manifest_data.get(
                "patientName", "Unknown Patient"
            ),
            "patientFolder": manifest_data.get("patientFolder", ""),
            "reviewStatus": manifest_data.get("reviewStatus", "REVIEWED"),
            "reviewedAt": manifest_data.get("reviewedAt"),
            "reviewerRemarks": manifest_data.get("reviewerRemarks", ""),
            "totalPages": manifest_data.get("totalPages", 0),
            "reviewedFolder": str(reviewed_root),
            "reviewedManifestPath": (
                str(reviewed_manifest_path)
                if reviewed_manifest_path
                else None
            ),
            "groups": grouped_documents,
            "files": files_in_reviewed_folder,
        },
    }



def upload_claim_packet_checklist_document(
    claim_id: str,
    checklist_item_id: str,
    file: UploadFile,
    document_type: str | None = None,
    display_name: str | None = None,
    reviewer_remarks: str | None = None,
) -> dict[str, Any]:
    upload_directory: Path | None = None

    try:
        clean_claim_id = str(
            claim_id or ""
        ).strip()

        clean_item_id = str(
            checklist_item_id or ""
        ).strip().upper()

        if not clean_claim_id:
            raise ValueError(
                "claim_id is required"
            )

        if not clean_item_id:
            raise ValueError(
                "checklist_item_id is required"
            )

        if file is None:
            raise ValueError(
                "file is required"
            )

        safe_filename = (
            _safe_upload_filename(
                file.filename
            )
        )

        extension = Path(
            safe_filename
        ).suffix.lower()

        if extension not in (
            ALLOWED_SUPPLEMENTAL_EXTENSIONS
        ):
            raise ValueError(
                "Only PDF documents are supported"
            )

        review_path, review_document = (
            get_or_create_checklist_review(
                clean_claim_id
            )
        )

        items = review_document.get(
            "items",
            [],
        )

        if not isinstance(items, list):
            items = []

        target_chk_id = _checklist_item_id(clean_item_id) if clean_item_id.isdigit() else clean_item_id

        selected_item = next(
            (
                item
                for item in items
                if str(
                    item.get("checklistItemId")
                    or ""
                ).upper() in (clean_item_id, target_chk_id)
                or str(
                    item.get("itemNo")
                    or ""
                ).upper() == clean_item_id
            ),
            None,
        )

        if selected_item is None:
            raise FileNotFoundError(
                "Checklist item not found: "
                f"{clean_item_id}"
            )

        system_status = str(
            selected_item.get(
                "systemStatus"
            )
            or ""
        ).upper()

        if system_status == "PRESENT":
            raise ValueError(
                "Document upload is not required "
                "because this checklist item is "
                "already present"
            )

        reviewer_decision = str(
            selected_item.get(
                "reviewerDecision"
            )
            or ""
        ).upper()

        reviewer_disposition = str(
            selected_item.get(
                "reviewerDisposition"
            )
            or ""
        ).upper()

        if (
            reviewer_decision != "REQUIRED"
            or reviewer_disposition
            != "REQUIRED_DOCUMENT_NEEDED"
        ):
            raise ValueError(
                "Checklist item must first be "
                "marked REQUIRED before uploading "
                "a missing document"
            )

        expected_document_types = (
            selected_item.get(
                "expectedDocumentTypes"
            )
            or []
        )

        if not isinstance(
            expected_document_types,
            list,
        ):
            expected_document_types = []

        clean_document_type = str(
            document_type or ""
        ).strip().upper()

        if not clean_document_type:
            clean_document_type = (
                str(
                    expected_document_types[0]
                ).strip().upper()
                if expected_document_types
                else "SUPPLEMENTAL_DOCUMENT"
            )

        clean_display_name = str(
            display_name or ""
        ).strip()

        if not clean_display_name:
            clean_display_name = str(
                selected_item.get(
                    "checklistItem"
                )
                or clean_document_type.replace(
                    "_",
                    " ",
                ).title()
            ).strip()

        clean_reviewer_remarks = str(
            reviewer_remarks or ""
        ).strip()

        uploaded_document_id = (
            f"upload-{uuid.uuid4().hex[:12]}"
        )

        supplemental_root = (
            _resolve_supplemental_root(
                clean_claim_id
            )
        )

        upload_directory = (
            supplemental_root
            / uploaded_document_id
        )

        upload_directory.mkdir(
            parents=True,
            exist_ok=False,
        )

        uploaded_file_path = (
            upload_directory
            / "original.pdf"
        )

        total_bytes = 0

        with uploaded_file_path.open(
            "wb"
        ) as destination:
            while True:
                chunk = file.file.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                total_bytes += len(chunk)

                if (
                    total_bytes
                    > MAX_SUPPLEMENTAL_FILE_SIZE
                ):
                    raise ValueError(
                        "Uploaded document exceeds "
                        "the 10 MB file-size limit"
                    )

                destination.write(chunk)

        if total_bytes == 0:
            raise ValueError(
                "Uploaded document is empty"
            )

        page_count = (
            _validate_supplemental_pdf(
                uploaded_file_path
            )
        )

        uploaded_at = (
            datetime.now().isoformat()
        )

        page_refs = [
            {
                "pageId": (
                    f"{uploaded_document_id}"
                    f"-page-{page_number:03d}"
                ),
                "sourceDocumentId": (
                    uploaded_document_id
                ),
                "sourceType": (
                    "REVIEWER_UPLOAD"
                ),
                "sourcePageNumber": (
                    page_number
                ),
            }
            for page_number in range(
                1,
                page_count + 1,
            )
        ]

        metadata = {
            "uploadedDocumentId": (
                uploaded_document_id
            ),
            "claimId": clean_claim_id,
            "checklistItemId": (
                clean_item_id
            ),
            "documentType": (
                clean_document_type
            ),
            "displayName": (
                clean_display_name
            ),
            "originalFileName": (
                safe_filename
            ),
            "storedFileName": (
                "original.pdf"
            ),
            "filePath": str(
                uploaded_file_path
            ),
            "fileSizeBytes": (
                total_bytes
            ),
            "pageCount": page_count,
            "pageRefs": page_refs,
            "reviewerRemarks": (
                clean_reviewer_remarks
            ),
            "assignmentStatus": (
                "UNASSIGNED"
            ),
            "assignedGroupId": None,
            "uploadedAt": uploaded_at,
            "previewUrl": (
                f"/api/claim-packets/"
                f"{clean_claim_id}"
                f"/uploaded-documents/"
                f"{uploaded_document_id}"
                f"/preview"
            ),
        }

        metadata_path = (
            upload_directory
            / "metadata.json"
        )

        with metadata_path.open(
            "w",
            encoding="utf-8",
        ) as metadata_file:
            json.dump(
                metadata,
                metadata_file,
                indent=2,
                ensure_ascii=False,
            )

        uploaded_document_ids = (
            selected_item.get(
                "uploadedDocumentIds"
            )
            or []
        )

        if not isinstance(
            uploaded_document_ids,
            list,
        ):
            uploaded_document_ids = []

        if (
            uploaded_document_id
            not in uploaded_document_ids
        ):
            uploaded_document_ids.append(
                uploaded_document_id
            )

        selected_item[
            "uploadedDocumentIds"
        ] = uploaded_document_ids

        selected_item[
            "reviewerDisposition"
        ] = "UPLOAD_PROVIDED"

        selected_item[
            "reviewerDecision"
        ] = "REQUIRED"

        selected_item[
            "reviewerRemarks"
        ] = (
            clean_reviewer_remarks
            or selected_item.get(
                "reviewerRemarks"
            )
            or ""
        )

        selected_item[
            "resolved"
        ] = True

        selected_item[
            "updatedAt"
        ] = uploaded_at

        _recalculate_checklist_review_summary(
            review_document
        )

        _write_checklist_review(
            path=review_path,
            review_document=review_document,
        )

        persisted_review = (
            _read_json_file(
                review_path
            )
        )

        persisted_item = next(
            (
                item
                for item in persisted_review.get(
                    "items",
                    [],
                )
                if str(
                    item.get(
                        "checklistItemId"
                    )
                    or ""
                ).upper()
                == clean_item_id
            ),
            None,
        )

        return {
            "success": True,
            "source": (
                "CHECKLIST_DOCUMENT_UPLOAD"
            ),
            "result": {
                "claimId": clean_claim_id,
                "checklistItem": (
                    persisted_item
                ),
                "uploadedDocument": (
                    metadata
                ),
                "summary": (
                    persisted_review.get(
                        "summary"
                    )
                ),
                "reviewStatus": (
                    persisted_review.get(
                        "reviewStatus"
                    )
                ),
            },
        }

    except FileNotFoundError as exc:
        if (
            upload_directory
            and upload_directory.exists()
        ):
            shutil.rmtree(
                upload_directory,
                ignore_errors=True,
            )

        return {
            "success": False,
            "source": (
                "CHECKLIST_DOCUMENT_UPLOAD"
            ),
            "errorCode": "NOT_FOUND",
            "error": str(exc),
        }

    except ValueError as exc:
        if (
            upload_directory
            and upload_directory.exists()
        ):
            shutil.rmtree(
                upload_directory,
                ignore_errors=True,
            )

        return {
            "success": False,
            "source": (
                "CHECKLIST_DOCUMENT_UPLOAD"
            ),
            "errorCode": (
                "VALIDATION_ERROR"
            ),
            "error": str(exc),
        }

    except Exception as exc:
        if (
            upload_directory
            and upload_directory.exists()
        ):
            shutil.rmtree(
                upload_directory,
                ignore_errors=True,
            )

        logger.exception(
            "Checklist document upload failed: "
            "claim_id=%s checklist_item_id=%s",
            claim_id,
            checklist_item_id,
        )

        return {
            "success": False,
            "source": (
                "CHECKLIST_DOCUMENT_UPLOAD"
            ),
            "errorCode": "INTERNAL_ERROR",
            "error": str(exc),
        }

    finally:
        try:
            file.file.close()
        except Exception:
            pass

ALLOWED_SUPPLEMENTAL_EXTENSIONS = {
    ".pdf",
}

MAX_SUPPLEMENTAL_FILE_SIZE = (
    10 * 1024 * 1024
)


def _safe_upload_filename(
    filename: str | None,
) -> str:
    original_name = Path(
        filename or "uploaded-document.pdf"
    ).name

    cleaned_name = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        original_name,
    ).strip("._")

    if not cleaned_name:
        cleaned_name = "uploaded-document.pdf"

    return cleaned_name


def _resolve_supplemental_root(
    claim_id: str,
) -> Path:
    manifest_path = (
        _resolve_review_manifest_path(
            claim_id
        )
    )

    return (
        manifest_path.parent
        / "supplemental"
    )


def _validate_supplemental_pdf(
    file_path: Path,
) -> int:
    if not file_path.exists():
        raise FileNotFoundError(
            f"Uploaded file not found: {file_path}"
        )

    try:
        reader = PdfReader(
            str(file_path)
        )
    except Exception as exc:
        raise ValueError(
            "Uploaded file is not a valid PDF"
        ) from exc

    page_count = len(reader.pages)

    if page_count <= 0:
        raise ValueError(
            "Uploaded PDF does not contain any pages"
        )

    return page_count


def _load_supplemental_documents(
    claim_id: str,
) -> list[dict[str, Any]]:
    supplemental_root = (
        _resolve_supplemental_root(
            claim_id
        )
    )

    if not supplemental_root.exists():
        return []

    documents: list[dict[str, Any]] = []

    for upload_directory in sorted(
        supplemental_root.iterdir()
    ):
        if not upload_directory.is_dir():
            continue

        metadata_path = (
            upload_directory
            / "metadata.json"
        )

        if not metadata_path.exists():
            continue

        try:
            metadata = _read_json_file(
                metadata_path
            )
        except Exception:
            logger.exception(
                "Unable to read supplemental metadata: %s",
                metadata_path,
            )
            continue

        uploaded_document_id = str(
            metadata.get(
                "uploadedDocumentId"
            )
            or upload_directory.name
        )

        metadata["uploadedDocumentId"] = (
            uploaded_document_id
        )

        metadata["previewUrl"] = (
            f"/api/claim-packets/{claim_id}"
            f"/uploaded-documents/"
            f"{uploaded_document_id}"
            f"/preview"
        )

        documents.append(metadata)

    return documents


def resolve_uploaded_document_preview(
    claim_id: str,
    uploaded_document_id: str,
) -> Path:
    clean_upload_id = str(
        uploaded_document_id or ""
    ).strip()

    if not clean_upload_id:
        raise ValueError(
            "uploaded_document_id is required"
        )

    supplemental_root = (
        _resolve_supplemental_root(
            claim_id
        )
    )

    document_path = (
        supplemental_root
        / clean_upload_id
        / "original.pdf"
    )

    if not document_path.exists():
        raise FileNotFoundError(
            "Uploaded document not found: "
            f"{clean_upload_id}"
        )

    return document_path

