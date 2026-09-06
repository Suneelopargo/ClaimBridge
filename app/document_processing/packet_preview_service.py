from pathlib import Path

from app.config import (
    CLAIM_PACKET_GROUPED_DIR,
    CLAIM_PACKET_SEGREGATED_DIR,
)

from app.document_processing.packet_storage import (
    read_json_file,
    resolve_claim_packet_manifest,
    resolve_review_manifest_path,
    resolve_supplemental_root,
)


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
    manifest_path = resolve_review_manifest_path(
        claim_id
    )

    manifest = read_json_file(
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

    reviewed_manifest = read_json_file(
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
        resolve_supplemental_root(
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
