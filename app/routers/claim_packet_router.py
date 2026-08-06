from pathlib import Path

import json

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    UploadFile,
    Query
)
from fastapi.responses import FileResponse

from app.config import CLAIM_PACKET_SEGREGATED_DIR
from app.schemas.claim_packet_review_schema import (
    SaveClaimPacketReviewRequest,
)

from app.schemas.claim_packet_checklist_review_schema import (
    ChecklistItemDecisionRequest,
)

from app.document_processing.packet_service import (
    classify_and_segregate_claim_packet,
    get_claim_packet_checklist_item_detail,
    get_claim_packet_checklist_review,
    get_claim_packet_review,
    get_claim_packet_reviewed_list,
    resolve_claim_packet_group_preview,
    resolve_claim_packet_page_preview,
    resolve_reviewed_group_preview,
    save_and_regenerate_claim_packet_review,
    update_claim_packet_checklist_item,
    validate_against_dispatch_checklist,
    upload_claim_packet_checklist_document, resolve_uploaded_document_preview,
)

from app.services.rule_engine.segregated_packet_inventory_service import (
    SegregatedPacketInventoryService,
)

from app.services.rule_engine.segregated_document_report_service import (
    SegregatedDocumentReportService,
)

from app.services.rule_engine.portfolio_validation_report_service import (
    PortfolioValidationReportService,
)

from app.services.rule_engine.portfolio_excel_service import (
    PortfolioExcelService,
)


router = APIRouter(
    prefix="/api/claim-packets",
    tags=["Claim Packet Processing"],
)


@router.post("/classify-and-segregate")
async def process_claim_packet(
    file: UploadFile = File(...),
    claim_id: str | None = Form(
        default=None
    ),
    patient_name: str | None = Form(
        default=None
    ),
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


# Reviewed list workspace
@router.get(
    "/{claim_id}/reviewedlist",
    summary="Get reviewed claim packet list",
    description="Reads and lists reviewed files and manifest under the claim ID /reviewed folder",
)
@router.get(
    "/{claim_id}/reviewed-list",
    include_in_schema=False,
)
def review_claim_packet_list(
    claim_id: str,
):
    try:
        return get_claim_packet_reviewed_list(
            claim_id=claim_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc



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


@router.get(
    "/{claim_id}/checklist-review",
    summary="Get Checklist Review Document",
    description="Returns the checklist review JSON document containing items, decisions, and statuses",
)
@router.get(
    "/{claim_id}/checklist-items",
    summary="Get Checklist Items Review Document",
    description="Alias to fetch the checklist_review.json document",
)
def get_checklist_review_document(claim_id: str):
    try:
        return get_claim_packet_checklist_review(claim_id=claim_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.get(
    "/{claim_id}/checklist-items/{checklist_item_id}",
    summary="Get Specific Checklist Item Details",
    description="Returns item detail containing checklistItemId, itemNo, systemStatus, etc., for the given item ID or item number",
)
@router.get(
    "/{claim_id}/checklist-review/items/{checklist_item_id}",
    summary="Get Specific Checklist Item Details (Alias)",
    description="Alias to fetch a single checklist item detail from checklist_review.json",
)
def get_checklist_item_detail(
    claim_id: str,
    checklist_item_id: str,
):
    try:
        return get_claim_packet_checklist_item_detail(
            claim_id=claim_id,
            checklist_item_id=checklist_item_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{claim_id}/checklist-items/"
    "{checklist_item_id}"
)
def update_checklist_item_decision(
    claim_id: str,
    checklist_item_id: str,
    request: ChecklistItemDecisionRequest,
):
    result = (
        update_claim_packet_checklist_item(
            claim_id=claim_id,
            checklist_item_id=(
                checklist_item_id
            ),
            payload=request.model_dump(),
        )
    )

    if result.get("success"):
        return result

    error_code = result.get(
        "errorCode"
    )

    if error_code == "NOT_FOUND":
        raise HTTPException(
            status_code=404,
            detail=result.get("error"),
        )

    if error_code == "VALIDATION_ERROR":
        raise HTTPException(
            status_code=422,
            detail=result.get("error"),
        )

    raise HTTPException(
        status_code=500,
        detail=result.get(
            "error",
            "Unable to update checklist item",
        ),
    )


@router.post(
    "/{claim_id}/checklist-items/"
    "{checklist_item_id}/documents"
)
def upload_missing_checklist_document(
    claim_id: str,
    checklist_item_id: str,
    file: UploadFile = File(...),
    documentType: str | None = Form(
        default=None
    ),
    displayName: str | None = Form(
        default=None
    ),
    reviewerRemarks: str | None = Form(
        default=None
    ),
):
    result = (
        upload_claim_packet_checklist_document(
            claim_id=claim_id,
            checklist_item_id=(
                checklist_item_id
            ),
            file=file,
            document_type=documentType,
            display_name=displayName,
            reviewer_remarks=(
                reviewerRemarks
            ),
        )
    )

    if result.get("success"):
        return result

    error_code = result.get(
        "errorCode"
    )

    if error_code == "NOT_FOUND":
        raise HTTPException(
            status_code=404,
            detail=result.get("error"),
        )

    if error_code == "VALIDATION_ERROR":
        raise HTTPException(
            status_code=422,
            detail=result.get("error"),
        )

    raise HTTPException(
        status_code=500,
        detail=result.get(
            "error",
            "Unable to upload document",
        ),
    )

@router.get(
    "/{claim_id}/uploaded-documents/"
    "{uploaded_document_id}/preview"
)
def preview_uploaded_document(
    claim_id: str,
    uploaded_document_id: str,
):
    try:
        path = resolve_uploaded_document_preview(
            claim_id=claim_id,
            uploaded_document_id=(
                uploaded_document_id
            ),
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



@router.get(
    "/document-reports/segregated-claims"
)
def list_segregated_claim_packets():
    try:
        service = (
            SegregatedPacketInventoryService()
        )

        items = service.list_claim_packets()

        return {
            "success": True,
            "source": (
                "SEGREGATED_PACKET_INVENTORY"
            ),
            "result": {
                "totalClaims": len(items),
                "claims": [
                    item.to_dict()
                    for item in items
                ],
            },
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.post(
    "/document-reports/"
    "segregated-claims/run-all"
)
def run_all_segregated_document_reports():
    try:
        service = (
            PortfolioValidationReportService()
        )

        portfolio = service.generate_all()

        return {
            "success": True,
            "source": (
                "SEGREGATED_PORTFOLIO_REPORT"
            ),
            "result": portfolio,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.get(
    "/document-reports/"
    "segregated-claims/{claim_id}"
)
def get_segregated_claim_packet(
    claim_id: str,
):
    try:
        service = (
            SegregatedPacketInventoryService()
        )

        item, manifest = (
            service.get_claim_packet(
                claim_id
            )
        )

        return {
            "success": True,
            "source": (
                "SEGREGATED_PACKET_INVENTORY"
            ),
            "result": {
                "claim": item.to_dict(),
                "documents": (
                    service.extract_documents(
                        manifest
                    )
                ),
            },
        }

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.post(
    "/document-reports/"
    "segregated-claims/{claim_id}/run"
)
def run_segregated_document_report(
    claim_id: str,
):
    try:
        service = (
            SegregatedDocumentReportService()
        )

        report = service.generate_report(
            claim_id
        )

        return {
            "success": True,
            "source": (
                "SEGREGATED_DOCUMENT_REPORT"
            ),
            "result": report.to_dict(),
        }

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.get(
    "/document-reports/"
    "portfolio/report"
)
def get_portfolio_validation_report():
    report_path = (
        CLAIM_PACKET_SEGREGATED_DIR.parent
        / "validation-reports"
        / "portfolio"
        / "portfolio_validation_report.json"
    )

    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Portfolio validation report "
                "has not been generated"
            ),
        )

    try:
        with report_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            result = json.load(file)

        return {
            "success": True,
            "source": (
                "SEGREGATED_PORTFOLIO_REPORT"
            ),
            "result": result,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.post(
    "/document-reports/portfolio/excel"
)
def generate_portfolio_excel():
    try:
        service = PortfolioExcelService()

        output_path = service.generate_excel()

        return {
            "success": True,
            "source": "PORTFOLIO_EXCEL_REPORT",
            "result": {
                "fileName": output_path.name,
                "filePath": str(output_path),
            },
        }

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.get(
    "/document-reports/portfolio/excel/download"
)
def download_portfolio_excel():
    try:
        service = PortfolioExcelService()

        output_path = (
            service.output_root
            / "portfolio"
            / "HCG_Claim_Validation_Report.xlsx"
        )

        if not output_path.exists():
            output_path = (
                service.generate_excel()
            )

        return FileResponse(
            path=str(output_path),
            filename=output_path.name,
            media_type=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.post(
    "/document-reports/portfolio/generate"
)
def generate_complete_portfolio_report():
    try:
        portfolio_service = (
            PortfolioValidationReportService()
        )

        portfolio = (
            portfolio_service.generate_all()
        )

        excel_service = PortfolioExcelService(
            output_root=(
                portfolio_service.output_root
            )
        )

        excel_path = (
            excel_service.generate_excel(
                portfolio=portfolio
            )
        )

        json_path = (
            portfolio_service.output_root
            / "portfolio"
            / "portfolio_validation_report.json"
        )

        return {
            "success": True,
            "source": (
                "COMPLETE_PORTFOLIO_REPORT"
            ),
            "result": {
                "summary": (
                    portfolio.get("summary")
                ),
                "portfolioInsights": (
                    portfolio.get(
                        "portfolioInsights"
                    )
                ),
                "jsonReportPath": str(
                    json_path
                ),
                "excelReportPath": str(
                    excel_path
                ),
                "excelFileName": (
                    excel_path.name
                ),
            },
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc