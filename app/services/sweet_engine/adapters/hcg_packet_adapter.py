# app/services/sweet_engine/adapters/hcg_packet_adapter.py

from __future__ import annotations

from typing import Any

from app.services.sweet_engine.context_resolver import ContextResolver
from app.services.sweet_engine.evidence_resolver import EvidenceResolver
from app.services.sweet_engine.page_inventory import PageInventory
from app.services.sweet_engine.boundary_resolver import (
    BoundaryResolver,
)


DOCUMENT_TYPE_ALIASES = {

    "CHEMO_THERAPY_ORDER_FORM": "TREATMENT_ORDER",
    "CHEMOTHERAPY_ORDER_FORM": "TREATMENT_ORDER",

    "CHEMO_THERAPY_ORDER": "TREATMENT_ORDER",
    "CHEMOTHERAPY_ORDER": "TREATMENT_ORDER",

    "RADIATION_THERAPY_ORDER_FORM": "TREATMENT_ORDER",
    "RADIOTHERAPY_ORDER_FORM": "TREATMENT_ORDER",

    "SURGERY_ORDER_FORM": "TREATMENT_ORDER",

}


def build_inventory_from_hcg_packet(
    *,
    packet_id: str,
    source_pdf_path: str,
    detected_pages: list[dict[str, Any]],
    run_context_resolution: bool = True,
    minimum_vision_confidence: float = 0.70,
) -> PageInventory:
    """
    Translate existing ClaimsBridge packet-processing output into
    a SWEET PageInventory.

    The adapter reuses existing Vision output. It does not render the
    PDF, invoke Vision, segregate pages, or create grouped PDFs.
    """

    normalized_packet_id = str(packet_id or "").strip()

    if not normalized_packet_id:
        raise ValueError("packet_id is required")

    if not detected_pages:
        raise ValueError(
            "detected_pages must contain at least one page"
        )

    source_path = str(source_pdf_path or "").strip()

    inventory = PageInventory(
        packet_id=normalized_packet_id,
        total_pages=len(detected_pages),
        source_pdf_path=source_path or None,
    )
    inventory.initialize_pages()

    seen_page_numbers: set[int] = set()

    for page_result in sorted(
        detected_pages,
        key=lambda item: _safe_page_number(
            item.get("pageNumber")
        ),
    ):
        page_number = _safe_page_number(
            page_result.get("pageNumber")
        )

        if page_number <= 0:
            raise ValueError(
                "Each detected page must contain a positive "
                "pageNumber"
            )

        if page_number in seen_page_numbers:
            raise ValueError(
                f"Duplicate pageNumber received: {page_number}"
            )

        if page_number > inventory.total_pages:
            raise ValueError(
                f"Page number {page_number} exceeds expected "
                f"packet page count {inventory.total_pages}"
            )

        seen_page_numbers.add(page_number)

        original_raw_type = str(
            page_result.get("rawDocumentType")
            or page_result.get("documentType")
            or "UNKNOWN"
        ).strip().upper()

        normalized_lookup = (
            original_raw_type
            .replace(" ", "_")
            .replace("-", "_")
        )

        normalized_raw_type = DOCUMENT_TYPE_ALIASES.get(
            normalized_lookup,
            original_raw_type,
        )

        classification = {
            "documentType": normalized_raw_type,
            "confidence": _safe_confidence(
                page_result.get("confidence")
            ),
            "reason": str(
                page_result.get("reason") or ""
            ).strip(),
            "patientName": str(
                page_result.get("patientName") or ""
            ).strip(),
            "claimNumber": str(
                page_result.get("claimNumber") or ""
            ).strip(),
            "mrn": str(
                page_result.get("mrn") or ""
            ).strip(),
            "ipNumber": str(
                page_result.get("ipNumber") or ""
            ).strip(),
            "payerName": str(
                page_result.get("payerName") or ""
            ).strip(),
            "billNumber": str(
                page_result.get("billNumber") or ""
            ).strip(),
            "documentDate": str(
                page_result.get("documentDate") or ""
            ).strip(),
            "totalAmount": str(
                page_result.get("totalAmount") or ""
            ).strip(),
        }

        inventory.apply_vision_result(
            page_number=page_number,
            classification=classification,
            extracted_text=str(
                page_result.get("extractedText") or ""
            ),
            minimum_confidence=minimum_vision_confidence,
        )

        inventory_page = inventory.get_page(page_number)

        inventory_page.evidence.custom_features.update({
            "productionDocumentType": str(
                page_result.get("documentType") or "UNKNOWN"
            ).strip().upper(),
            "originalRawDocumentType": original_raw_type,
            "normalizedRawDocumentType": normalized_raw_type,
            # Retained for backward compatibility with earlier reports.
            "rawDocumentType": normalized_raw_type,
            "qualityStatus": str(
                page_result.get("qualityStatus") or ""
            ).strip(),
            "normalizationSource": str(
                page_result.get("normalizationSource") or ""
            ).strip(),
            "source": str(
                page_result.get("source") or ""
            ).strip(),

            # Rich Vision evidence required by BUCKET_V2 and semantic
            # sequence refinement.
            "visibleTitle": str(
                page_result.get("visibleTitle") or ""
            ).strip(),
            "sectionTitle": str(
                page_result.get("sectionTitle") or ""
            ).strip(),
            "pageRole": str(
                page_result.get("pageRole") or "UNKNOWN"
            ).strip().upper(),
            "printedPageNumber": page_result.get(
                "printedPageNumber"
            ),
            "printedTotalPages": page_result.get(
                "printedTotalPages"
            ),
            "explicitDocumentStart": bool(
                page_result.get("explicitDocumentStart", False)
            ),
            "explicitDocumentEnd": bool(
                page_result.get("explicitDocumentEnd", False)
            ),
            "standaloneDocument": bool(
                page_result.get("standaloneDocument", False)
            ),
            "templateHint": str(
                page_result.get("templateHint") or ""
            ).strip(),
            "templateSignature": str(
                page_result.get("templateHint") or ""
            ).strip(),
            "headerSignature": str(
                page_result.get("headerSignature") or ""
            ).strip(),
            "footerSignature": str(
                page_result.get("footerSignature") or ""
            ).strip(),
            "continuationIndicators": list(
                page_result.get("continuationIndicators") or []
            ),
            "candidateDocumentTypes": list(
                page_result.get("candidateDocumentTypes") or []
            ),
            "authorizationNumber": str(
                page_result.get("authorizationNumber") or ""
            ).strip(),
            "policyNumber": str(
                page_result.get("policyNumber") or ""
            ).strip(),
            "memberId": str(
                page_result.get("memberId") or ""
            ).strip(),
            "reason": str(
                page_result.get("reason") or ""
            ).strip(),
        })

    inventory.assert_no_page_drop()

    EvidenceResolver().resolve_inventory(inventory)

    if run_context_resolution:
        ContextResolver().resolve_inventory(inventory)
    BoundaryResolver().resolve_inventory(inventory)

    inventory.assert_no_page_drop()

    return inventory


def build_inventory_from_packet_manifest(
    manifest: dict[str, Any],
    *,
    run_context_resolution: bool = True,
    minimum_vision_confidence: float = 0.70,
) -> PageInventory:
    """
    Build an inventory from packet_service.py manifest output.
    """

    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a dictionary")

    packet_id = str(
        manifest.get("claimId")
        or manifest.get("packetId")
        or ""
    ).strip()

    source_pdf_path = str(
        manifest.get("sourceFile") or ""
    ).strip()

    detected_pages = manifest.get("documentsDetected") or []

    if not isinstance(detected_pages, list):
        raise ValueError(
            "manifest.documentsDetected must be a list"
        )

    inventory = build_inventory_from_hcg_packet(
        packet_id=packet_id,
        source_pdf_path=source_pdf_path,
        detected_pages=detected_pages,
        run_context_resolution=run_context_resolution,
        minimum_vision_confidence=minimum_vision_confidence,
    )

    # Preserve packet-level patient identity for semantic role refinement.
    inventory.packet_patient_name = str(
        manifest.get("patientName") or ""
    ).strip()

    return inventory


def _safe_page_number(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.0

    return max(0.0, min(1.0, confidence))
