import json
import logging
import re
import shutil
import uuid

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from pypdf import PdfReader

from app.document_processing.checklist_review_service import (
    apply_uploaded_document_to_checklist_review,
    find_checklist_review_item,
    get_or_create_checklist_review,
)
from app.document_processing.packet_storage import (
    read_json_file,
    resolve_supplemental_root,
)

logger = logging.getLogger(__name__)

ALLOWED_SUPPLEMENTAL_EXTENSIONS = {
    ".pdf",
}

MAX_SUPPLEMENTAL_FILE_SIZE = (
    10 * 1024 * 1024
)

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

        selected_item = find_checklist_review_item(
            review_document=review_document,
            checklist_item_id=clean_item_id,
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
            resolve_supplemental_root(
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

        persisted_review, persisted_item = (
            apply_uploaded_document_to_checklist_review(
                review_path=review_path,
                review_document=review_document,
                checklist_item_id=clean_item_id,
                uploaded_document_id=uploaded_document_id,
                reviewer_remarks=clean_reviewer_remarks,
                updated_at=uploaded_at,
            )
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


def load_supplemental_documents(
    claim_id: str,
) -> list[dict[str, Any]]:
    supplemental_root = (
        resolve_supplemental_root(
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
            metadata = read_json_file(
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
