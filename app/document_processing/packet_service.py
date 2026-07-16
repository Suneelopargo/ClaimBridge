from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pdf2image import convert_from_bytes
from openai import OpenAI
from PIL import Image
from dotenv import load_dotenv
import tempfile
import os
import json
import base64
import smtplib
from email.mime.text import MIMEText
from pydantic import BaseModel
from datetime import datetime
import imaplib
import email
import re
from email.header import decode_header
from datetime import datetime, timedelta
import random
import requests
from fastapi import UploadFile, File
from pypdf import PdfReader, PdfWriter
import shutil
import json
from pathlib import Path
import time
from email.utils import parsedate_to_datetime
from app.config import (
    CLAIM_PACKET_GROUPED_DIR,
    CLAIM_PACKET_INPUT_DIR,
    CLAIM_PACKET_SEGREGATED_DIR,
)
import os

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


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


def patient_name_from_filename(filename: str) -> str:
    stem = Path(filename).stem

    # Examples:
    # 14.07.vijaya.pdf -> Vijaya
    # 14-07-vijaya.pdf -> Vijaya
    # 4325_customer_packet.pdf -> Customer Packet
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

    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned.title() if cleaned else "Unknown Patient"


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
    Generic normalization for newly uploaded customer PDFs.

    Important:
    - No fixed page-number rules.
    - No Jain Sangita-specific mappings.
    - Low-confidence pages are marked UNKNOWN.
    """

    normalized = dict(item)

    document_type = str(
        item.get("documentType") or "UNKNOWN"
    ).upper().strip()

    confidence = float(item.get("confidence") or 0)

    allowed_types = {
        "COVERING_LETTER",
        "CLAIM_FORM",
        "GIPSA_DECLARATION",
        "APPROVAL_LETTER",
        "GOP_PRE_APPROVAL",
        "GOP_FINAL_APPROVAL",
        "CASHLESS_AUTHORIZATION_LETTER",
        "PREAUTHORIZATION_FORM",
        "KYC_DOCUMENT",
        "PROPOSER_ID_PROOF",
        "PATIENT_ID_PROOF",
        "PATIENT_PHOTO",
        "FINAL_HOSPITAL_BILL",
        "DETAILED_BILL_BREAKUP",
        "BILL_CONTINUATION",
        "DISCHARGE_SUMMARY",
        "PAYMENT_RECEIPT",
        "REFUND_RECEIPT",
        "CASE_PAPER",
        "OT_NOTES",
        "INVESTIGATION_REPORT",
        "LAB_REPORT",
        "RADIOLOGY_REPORT",
        "PHARMACY_BILL",
        "PHARMACY_DETAILS",
        "IMPLANT_STICKER_INVOICE",
        "BLOOD_COMPONENT_STICKER",
        "CONSENT_FORM",
        "PRESCRIPTION",
        "NON_MEDICAL_DETAILS",
        "CHECKLIST",
    }

    if document_type not in allowed_types or confidence < 0.70:
        document_type = "UNKNOWN"

    normalized["documentType"] = document_type
    normalized["normalized"] = False
    normalized["normalizationSource"] = "GENERIC_VISION_CLASSIFIER"
    normalized["reviewRequired"] = document_type == "UNKNOWN"

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


async def classify_and_segregate_claim_packet(
    file: UploadFile = File(...),
    claim_id: str | None = None,
    patient_name: str | None = None,
):
    """
    Generic customer claim packet processor.

    Flow:
    1. Save uploaded PDF.
    2. Render every page as an image.
    3. Classify each page using OpenAI Vision.
    4. Derive patient and claim metadata dynamically.
    5. Save individual segregated pages.
    6. Build grouped payer-ready PDFs.
    7. Build dispatch checklist status.
    8. Create manifest.json.
    """

    temp_image_paths: list[str] = []

    try:
        # ---------------------------------------------------------
        # Step 1: Save uploaded PDF
        # ---------------------------------------------------------
        base_upload_dir = CLAIM_PACKET_INPUT_DIR
        base_upload_dir.mkdir(parents=True, exist_ok=True)

        safe_input_name = Path(file.filename or "customer-packet.pdf").name
        input_pdf_path = base_upload_dir / safe_input_name

        with open(input_pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        reader = PdfReader(str(input_pdf_path))

        if len(reader.pages) == 0:
            raise ValueError("Uploaded PDF does not contain any pages")

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

            classification = classify_page_with_vision(image_path)
            classification["source"] = "OPENAI_VISION"

            document_type = str(
                classification.get("documentType") or "UNKNOWN"
            ).upper().strip()

            try:
                confidence = float(
                    classification.get("confidence") or 0
                )
            except (TypeError, ValueError):
                confidence = 0.0

            if confidence < 0.70:
                document_type = "UNKNOWN"

            raw_docs.append({
                "pageNumber": page_number,
                "documentType": document_type,
                "rawDocumentType": str(
                    classification.get("documentType") or "UNKNOWN"
                ).upper().strip(),
                "confidence": confidence,
                "source": classification.get("source"),
                "reason": classification.get("reason", ""),
                "patientName": classification.get("patientName", ""),
                "claimNumber": classification.get("claimNumber", ""),
                "mrn": classification.get("mrn", ""),
                "ipNumber": classification.get("ipNumber", ""),
                "payerName": classification.get("payerName", ""),
                "billNumber": classification.get("billNumber", ""),
                "documentDate": classification.get("documentDate", ""),
                "totalAmount": classification.get("totalAmount", ""),
                "qualityStatus": (
                    "TEXT_READABLE"
                    if page_text.strip()
                    else "SCANNED_IMAGE"
                ),
            })

        # ---------------------------------------------------------
        # Step 3: Derive patient and claim metadata dynamically
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
        patient_folder = safe_folder_name(final_patient_name)

        segregated_dir =CLAIM_PACKET_SEGREGATED_DIR / final_claim_id

        claim_pack_dir = CLAIM_PACKET_GROUPED_DIR / patient_folder

        # Remove stale output from earlier processing attempts.
        if segregated_dir.exists():
            shutil.rmtree(segregated_dir)

        if claim_pack_dir.exists():
            shutil.rmtree(claim_pack_dir)

        segregated_dir.mkdir(parents=True, exist_ok=True)
        claim_pack_dir.mkdir(parents=True, exist_ok=True)

        # ---------------------------------------------------------
        # Step 4: Generic page normalization
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

        # ---------------------------------------------------------
        # Step 5: Write individual segregated page PDFs
        # ---------------------------------------------------------
        for item in detected_docs:
            page_index = item["pageNumber"] - 1
            output_file = item["outputFile"]

            segregated_file_path = (
                segregated_dir / output_file
            )

            write_single_page_pdf(
                reader,
                page_index,
                segregated_file_path,
            )

            item["segregatedFile"] = str(
                segregated_file_path
            )

        # ---------------------------------------------------------
        # Step 6: Build grouped payer-ready PDFs
        # ---------------------------------------------------------
        grouped_documents = build_grouped_documents(
            reader=reader,
            detected_docs=detected_docs,
            output_dir=claim_pack_dir,
        )

        # ---------------------------------------------------------
        # Step 7: Build dispatch checklist mapping
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
                "rawDocumentType": item.get("rawDocumentType"),
                "confidence": item.get("confidence"),
                "reason": item.get("reason", ""),
            }
            for item in detected_docs
            if item.get("reviewRequired")
        ]

        identified_pages = len([
            item
            for item in detected_docs
            if item.get("documentType") != "UNKNOWN"
        ])

        # ---------------------------------------------------------
        # Step 8: Build and save manifest
        # ---------------------------------------------------------
        manifest = {
            "claimId": final_claim_id,
            "patientName": final_patient_name,
            "patientFolder": patient_folder,
            "sourceFile": str(input_pdf_path),
            "segregatedFolder": str(segregated_dir),
            "claimPackFolder": str(claim_pack_dir),
            "totalPages": len(reader.pages),
            "documentsDetected": detected_docs,
            "groupedDocuments": grouped_documents,
            "checklistStatus": checklist_status,
            "reviewRequiredPages": review_required_pages,
            "summary": {
                "totalPages": len(reader.pages),
                "identifiedPages": identified_pages,
                "groupedDocumentCount": len(grouped_documents),
                "reviewRequiredPages": len(review_required_pages),
                "status": (
                    "REVIEW_REQUIRED"
                    if review_required_pages
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

        with open(
            segregated_manifest_path,
            "w",
            encoding="utf-8",
        ) as manifest_file:
            json.dump(
                manifest,
                manifest_file,
                indent=2,
                ensure_ascii=False,
            )

        with open(
            claim_pack_manifest_path,
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
            "source": "GENERIC_VISION_PACKET_PROCESSING",
            "result": manifest,
        }

    except Exception as exc:
        print(
            "CLAIM PACKET PROCESSING ERROR:",
            repr(exc),
        )

        return {
            "success": False,
            "source": "GENERIC_VISION_PACKET_PROCESSING",
            "error": str(exc),
        }

    finally:
        # Always delete temporary page images.
        for image_path in temp_image_paths:
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
            except Exception:
                pass


def classify_page_with_vision(image_path: str):
    base64_image = image_to_base64(image_path)

    prompt = """
You are classifying one page from a real Indian hospital insurance claim packet.

Return STRICT JSON only.

Fields:
{
  "documentType": "",
  "patientName": "",
  "claimNumber": "",
  "mrn": "",
  "ipNumber": "",
  "payerName": "",
  "billNumber": "",
  "documentDate": "",
  "totalAmount": "",
  "confidence": 0.0,
  "reason": ""
}

Allowed documentType values:
COVERING_LETTER,
CLAIM_FORM,
GIPSA_DECLARATION,
APPROVAL_LETTER,
PREAUTHORIZATION_FORM,
KYC_DOCUMENT,
PATIENT_ID_PROOF,
PATIENT_PHOTO,
FINAL_HOSPITAL_BILL,
DETAILED_BILL_BREAKUP,
BILL_CONTINUATION,
DISCHARGE_SUMMARY,
PAYMENT_RECEIPT,
REFUND_RECEIPT,
CASE_PAPER,
OT_NOTES,
INVESTIGATION_REPORT,
LAB_REPORT,
RADIOLOGY_REPORT,
PHARMACY_BILL,
PHARMACY_DETAILS,
IMPLANT_STICKER_INVOICE,
CONSENT_FORM,
PRESCRIPTION,
NON_MEDICAL_DETAILS,
CHECKLIST,
UNKNOWN

Rules:
- This may be scanned, handwritten, stamped, rotated, or low quality.
- If it is a continuation page of a hospital bill, use BILL_CONTINUATION.
- If unsure, return UNKNOWN with low confidence.
- Do not invent missing values.
- Classify using the visible document title, heading, table structure, and form labels.
- Do not classify only because another document name appears somewhere in body text.
- A dispatch checklist must be classified as CHECKLIST.
- A final hospital bill must visibly contain billing totals, invoice details, patient billing details, or line-item charges.
- A discharge summary must visibly contain diagnosis, hospital course, treatment, procedure, discharge condition, or follow-up advice.
- If the visible title and page content conflict, return UNKNOWN.
- If confidence is below 0.70, return UNKNOWN.
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": "You classify scanned healthcare claim packet pages.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        },
                    },
                ],
            },
        ],
        temperature=0,
    )

    try:
        return clean_json_response(response.choices[0].message.content)
    except Exception:
        return {
            "documentType": "UNKNOWN",
            "confidence": 0.2,
            "reason": "Vision response could not be parsed",
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
            if doc.get("groupCode") in rule.get("groupCodes", [])
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
