import json
from pathlib import Path
from typing import Any

from app.config import (
    CLAIM_PACKET_GROUPED_DIR,
    CLAIM_PACKET_SEGREGATED_DIR,
)


def read_json_file(path: Path) -> dict[str, Any]:
    """
    Read and validate a JSON object from disk.
    """

    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON file: {path}"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            f"Expected JSON object in file: {path}"
        )

    return payload


def resolve_review_manifest_path(
    claim_id: str,
) -> Path:
    """
    Resolve the most appropriate manifest for document review.

    Priority:
    1. Use the claim-pack manifest when available.
    2. Fall back to the segregated claim manifest.
    """

    segregated_manifest_path = (
        CLAIM_PACKET_SEGREGATED_DIR
        / claim_id
        / "manifest.json"
    )

    if segregated_manifest_path.exists():
        segregated_manifest = read_json_file(
            segregated_manifest_path
        )

        patient_folder = str(
            segregated_manifest.get("patientFolder")
            or ""
        ).strip()

        if patient_folder:
            claim_pack_manifest_path = (
                CLAIM_PACKET_GROUPED_DIR
                / patient_folder
                / "manifest.json"
            )

            if claim_pack_manifest_path.exists():
                return claim_pack_manifest_path

        claim_pack_folder = str(
            segregated_manifest.get("claimPackFolder")
            or ""
        ).strip()

        if claim_pack_folder:
            claim_pack_manifest_path = (
                Path(claim_pack_folder)
                / "manifest.json"
            )

            if claim_pack_manifest_path.exists():
                return claim_pack_manifest_path

    if segregated_manifest_path.exists():
        return segregated_manifest_path

    raise FileNotFoundError(
        f"No review manifest found for claim_id={claim_id}"
    )


def resolve_claim_packet_manifest(
    claim_id: str,
) -> tuple[Path, dict]:
    clean_claim_id = str(claim_id or "").strip()

    if not clean_claim_id:
        raise ValueError("claim_id is required")

    manifest_path = (
        CLAIM_PACKET_SEGREGATED_DIR
        / clean_claim_id
        / "manifest.json"
    )

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Claim packet manifest not found: {manifest_path}"
        )

    manifest = read_json_file(manifest_path)

    return manifest_path, manifest


def resolve_claim_packet_source_pdf(
    claim_id: str,
) -> tuple[Path, dict]:
    _, manifest = resolve_claim_packet_manifest(
        claim_id
    )

    source_file = str(
        manifest.get("sourceFile") or ""
    ).strip()

    if not source_file:
        raise ValueError(
            "sourceFile is missing from claim manifest"
        )

    source_pdf_path = Path(source_file)

    if not source_pdf_path.exists():
        raise FileNotFoundError(
            f"Source PDF not found: {source_pdf_path}"
        )

    return source_pdf_path, manifest


def resolve_supplemental_root(
    claim_id: str,
) -> Path:
    manifest_path = resolve_review_manifest_path(
        claim_id
    )

    return (
        manifest_path.parent
        / "supplemental"
    )
