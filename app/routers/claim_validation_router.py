from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.mappers.claim_validation_mapper import ClaimValidationMapper

from app.schemas.claim_validation import (
    ClaimValidationRequest,
    ValidationRunResponse,
)

from app.services.rule_engine.orchestrator_factory import (
    build_validation_orchestrator,
)

router = APIRouter(
    prefix="/api/claim-validation",
    tags=["Claim Validation"],
)


@router.post(
    "/run",
    response_model=ValidationRunResponse,
)
def run_validation(
    request: ClaimValidationRequest,
    db: Session = Depends(get_db),
):

    try:

        orchestrator = build_validation_orchestrator(db)

        report = orchestrator.run_validation(
            claim_id=request.claim_id,
            payer_code=request.payer_code,
            patient_name=request.patient_name,
            manifest=request.manifest,
            source_manifest_path=request.source_manifest_path,
        )
        print(request)
        print(request.payer_code)
        return ClaimValidationMapper.to_response(report)

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )