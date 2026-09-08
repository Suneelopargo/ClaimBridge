import json
import logging
import re
import shutil

from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pypdf import PdfReader

from app.config import (
    CLAIM_PACKET_GROUPED_DIR,
    CLAIM_PACKET_SEGREGATED_DIR,
)

from app.document_processing.packet_pdf_service import (
    write_merged_pdf,
)

from app.document_processing.packet_storage import (
    read_json_file,
    resolve_claim_packet_source_pdf,
    resolve_review_manifest_path,
)

from app.document_processing.supplemental_document_service import (
    load_supplemental_documents,
)

logger = logging.getLogger(__name__)


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

    manifest_path = resolve_review_manifest_path(
        clean_claim_id
    )

    try:
        manifest = read_json_file(manifest_path)

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
            load_supplemental_documents(
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
        manifest = read_json_file(segregated_manifest_path)
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
        reviewed_manifest = read_json_file(
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
