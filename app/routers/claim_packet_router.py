from pathlib import Path

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse

from app.document_processing.packet_service import (
    classify_and_segregate_claim_packet,
    get_claim_packet_review,
    resolve_claim_packet_group_preview,
    resolve_claim_packet_page_preview,
    resolve_reviewed_group_preview,
    save_and_regenerate_claim_packet_review,
    validate_against_dispatch_checklist,
)
from app.schemas.claim_packet_review_schema import (
    SaveClaimPacketReviewRequest,
)


router = APIRouter(
    prefix="/api/claim-packets",
    tags=["Claim Packet Processing"],
)


@router.post("/classify-and-segregate")
async def process_claim_packet(
    file: UploadFile = File(...),
    claim_id: str | None = None,
    patient_name: str | None = None,
):
    filename = Path(
        file.filename or ""
    ).name

    if not filename.lower().endswith(".pdf"):
        return {
            "success": False,
            "source": "SWEET_RESOLVER_PACKET_PROCESSING",
            "error": "Only PDF claim packets are supported",
        }

    try:
        return await classify_and_segregate_claim_packet(
            file=file,
            claim_id=claim_id,
            patient_name=patient_name,
        )
    finally:
        await file.close()


# Review workspace
@router.get("/{claim_id}/review")
def review_claim_packet(
    claim_id: str,
):
    return get_claim_packet_review(
        claim_id=claim_id,
    )


# Individual page preview
@router.get(
    "/{claim_id}/pages/{page_number}/preview"
)
def preview_claim_packet_page(
    claim_id: str,
    page_number: int,
):
    try:
        path = resolve_claim_packet_page_preview(
            claim_id=claim_id,
            page_number=page_number,
        )

        return FileResponse(
            path=str(path),
            media_type="application/pdf",
            filename=path.name,
            content_disposition_type="inline",
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


# Existing AI group preview
@router.get(
    "/{claim_id}/groups/{group_id}/preview"
)
def preview_claim_packet_group(
    claim_id: str,
    group_id: str,
):
    try:
        path = resolve_claim_packet_group_preview(
            claim_id=claim_id,
            group_id=group_id,
        )

        return FileResponse(
            path=str(path),
            media_type="application/pdf",
            filename=path.name,
            content_disposition_type="inline",
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


# Save and regenerate
@router.put("/{claim_id}/review")
def save_claim_packet_review(
    claim_id: str,
    request: SaveClaimPacketReviewRequest,
):
    return save_and_regenerate_claim_packet_review(
        claim_id=claim_id,
        payload=request.model_dump(),
    )


# Reviewed group preview
@router.get(
    "/{claim_id}/reviewed-groups/{group_id}/preview"
)
def preview_reviewed_claim_packet_group(
    claim_id: str,
    group_id: str,
):
    try:
        path = resolve_reviewed_group_preview(
            claim_id=claim_id,
            group_id=group_id,
        )

        return FileResponse(
            path=str(path),
            media_type="application/pdf",
            filename=path.name,
            content_disposition_type="inline",
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.post("/validate-checklist")
def validate_packet(claim_id: str):
    return validate_against_dispatch_checklist(
        claim_id=claim_id,
    )