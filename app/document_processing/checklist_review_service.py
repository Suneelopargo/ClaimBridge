import json
import logging
import re

from datetime import datetime
from pathlib import Path
from typing import Any

from app.document_processing.checklist_validation_service import (
    validate_against_dispatch_checklist,
)
from app.document_processing.packet_storage import (
    read_json_file,
    resolve_review_manifest_path,
)

logger = logging.getLogger(__name__)

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
    manifest_path = resolve_review_manifest_path(
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
            read_json_file(review_path),
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

        previous_decision = selected_item.get(
            "reviewerDecision"
        )

        previous_disposition = selected_item.get(
            "reviewerDisposition"
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

        _recalculate_checklist_review_summary(
            review_document
        )

        _write_checklist_review(
            path=review_path,
            review_document=review_document,
        )

        persisted_review = read_json_file(
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

def find_checklist_review_item(
    review_document: dict,
    checklist_item_id: str,
) -> dict | None:
    clean_item_id = str(
        checklist_item_id or ""
    ).strip().upper()

    if not clean_item_id:
        return None

    items = review_document.get("items", [])

    if not isinstance(items, list):
        return None

    target_chk_id = (
        _checklist_item_id(clean_item_id)
        if clean_item_id.isdigit()
        else clean_item_id
    )

    return next(
        (
            item
            for item in items
            if str(
                item.get("checklistItemId") or ""
            ).upper()
            in (clean_item_id, target_chk_id)
            or str(
                item.get("itemNo") or ""
            ).upper()
            == clean_item_id
        ),
        None,
    )


def apply_uploaded_document_to_checklist_review(
    review_path: Path,
    review_document: dict,
    checklist_item_id: str,
    uploaded_document_id: str,
    reviewer_remarks: str,
    updated_at: str,
) -> tuple[dict[str, Any], dict]:
    selected_item = find_checklist_review_item(
        review_document=review_document,
        checklist_item_id=checklist_item_id,
    )

    if selected_item is None:
        raise FileNotFoundError(
            f"Checklist item not found: {checklist_item_id}"
        )

    uploaded_document_ids = (
        selected_item.get("uploadedDocumentIds")
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
        reviewer_remarks
        or selected_item.get(
            "reviewerRemarks"
        )
        or ""
    )

    selected_item["resolved"] = True
    selected_item["updatedAt"] = updated_at

    _recalculate_checklist_review_summary(
        review_document
    )

    _write_checklist_review(
        path=review_path,
        review_document=review_document,
    )

    persisted_review = read_json_file(
        review_path
    )

    persisted_item = (
        find_checklist_review_item(
            review_document=persisted_review,
            checklist_item_id=checklist_item_id,
        )
    )

    if persisted_item is None:
        raise RuntimeError(
            "Checklist item was not found after save"
        )

    return persisted_review, persisted_item
