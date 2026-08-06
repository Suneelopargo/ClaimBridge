from __future__ import annotations

import json
import logging

from pathlib import Path
from typing import Any

from app.config import (
    CLAIM_PACKET_SEGREGATED_DIR,
)
from app.services.rule_engine.document_report_models import (
    ClaimPacketInventoryItem,
)


logger = logging.getLogger(__name__)


class SegregatedPacketInventoryService:
    """
    Discovers processed claim packets under:

        data/segregated/<claimId>

    Every valid packet must contain manifest.json.
    """

    def __init__(
        self,
        segregated_root: Path | None = None,
    ) -> None:
        self.segregated_root = (
            segregated_root
            or CLAIM_PACKET_SEGREGATED_DIR
        )

    def list_claim_packets(
        self,
    ) -> list[ClaimPacketInventoryItem]:
        if not self.segregated_root.exists():
            return []

        items: list[
            ClaimPacketInventoryItem
        ] = []

        for claim_directory in sorted(
            self.segregated_root.iterdir()
        ):
            if not claim_directory.is_dir():
                continue

            manifest_path = (
                claim_directory
                / "manifest.json"
            )

            if not manifest_path.exists():
                logger.warning(
                    "Skipping segregated folder "
                    "without manifest: %s",
                    claim_directory,
                )
                continue

            try:
                manifest = self._read_json(
                    manifest_path
                )

                item = self._build_inventory_item(
                    claim_directory=(
                        claim_directory
                    ),
                    manifest_path=manifest_path,
                    manifest=manifest,
                )

                items.append(item)

            except Exception:
                logger.exception(
                    "Unable to inspect "
                    "segregated packet: %s",
                    claim_directory,
                )

        return items

    def get_claim_packet(
        self,
        claim_id: str,
    ) -> tuple[
        ClaimPacketInventoryItem,
        dict[str, Any],
    ]:
        clean_claim_id = str(
            claim_id or ""
        ).strip()

        if not clean_claim_id:
            raise ValueError(
                "claim_id is required"
            )

        claim_directory = (
            self.segregated_root
            / clean_claim_id
        )

        manifest_path = (
            claim_directory
            / "manifest.json"
        )

        if not manifest_path.exists():
            raise FileNotFoundError(
                "Segregated claim packet "
                f"not found: {clean_claim_id}"
            )

        manifest = self._read_json(
            manifest_path
        )

        item = self._build_inventory_item(
            claim_directory=claim_directory,
            manifest_path=manifest_path,
            manifest=manifest,
        )

        return item, manifest

    @staticmethod
    def _build_inventory_item(
        *,
        claim_directory: Path,
        manifest_path: Path,
        manifest: dict[str, Any],
    ) -> ClaimPacketInventoryItem:
        claim_id = str(
            manifest.get("claimId")
            or manifest.get("packetId")
            or claim_directory.name
        ).strip()

        patient_name = str(
            manifest.get("patientName")
            or ""
        ).strip() or None

        patient_folder = str(
            manifest.get("patientFolder")
            or ""
        ).strip() or None

        documents = (
            SegregatedPacketInventoryService
            .extract_documents(manifest)
        )

        processing_status = str(
            (
                manifest.get("summary")
                or {}
            ).get("status")
            or ""
        ).strip() or None

        return ClaimPacketInventoryItem(
            claim_id=claim_id,
            patient_name=patient_name,
            patient_folder=patient_folder,
            claim_directory=str(
                claim_directory
            ),
            source_manifest_path=str(
                manifest_path
            ),
            source_manifest_type=(
                "SEGREGATED_MANIFEST"
            ),
            document_count=len(documents),
            review_status=processing_status,
        )

    @staticmethod
    def extract_documents(
        manifest: dict[str, Any],
    ) -> list[dict[str, Any]]:
        documents = manifest.get(
            "documentsDetected"
        )

        if not isinstance(documents, list):
            return []

        return [
            item
            for item in documents
            if isinstance(item, dict)
        ]

    @staticmethod
    def _read_json(
        path: Path,
    ) -> dict[str, Any]:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError(
                "Segregated manifest must "
                "contain a JSON object"
            )

        return data