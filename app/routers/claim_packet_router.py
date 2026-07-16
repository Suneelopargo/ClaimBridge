from fastapi import APIRouter, File, UploadFile

from app.document_processing.packet_service import (
    classify_and_segregate_claim_packet,
    validate_against_dispatch_checklist
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
    return await classify_and_segregate_claim_packet(
        file=file,
        claim_id=claim_id,
        patient_name=patient_name,
    )


@router.post("/validate-checklist")
def validate_packet(claim_id: str):
    return validate_against_dispatch_checklist(
        claim_id=claim_id,
    )