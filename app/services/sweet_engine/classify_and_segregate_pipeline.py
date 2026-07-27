# app/services/sweet_engine/classify_and_segregate_pipeline.py

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.services.sweet_engine.boundary_resolver import (
    BoundaryResolver,
)
from app.services.sweet_engine.document_group_resolver import (
    DocumentGroupResolver,
)
from app.services.sweet_engine.document_identity_resolver import (
    DocumentIdentityResolver,
)
from app.services.sweet_engine.physical_document_builder import (
    PhysicalDocumentBuilder,
)
from app.services.sweet_engine_v2.document_bucket_resolver import (
    DocumentBucketResolver,
)
from app.services.sweet_engine_v2.document_sequence_refiner import (
    DocumentSequenceRefiner,
)
from app.services.sweet_engine_v2.identity_role_resolver import (
    IdentityRoleResolver,
)


LEGACY_GROUPING_ENGINE = "LEGACY"
BUCKET_GROUPING_ENGINE = "BUCKET_V2"
DEFAULT_GROUPING_ENGINE = BUCKET_GROUPING_ENGINE


@dataclass
class ClassifyAndSegregateResult:
    packet_id: str
    total_pages: int
    group_count: int
    logical_grouping_integrity_valid: bool
    physical_grouping_integrity_valid: bool
    grouped_manifest_path: str
    output_directory: str
    documents: list[dict[str, Any]]


class ClassifyAndSegregatePipeline:
    """
    Orchestration layer used by the API endpoint.

    The caller is responsible for:
      1. saving the uploaded PDF;
      2. producing the PageInventory using the existing
         classification/context pipeline;
      3. passing both the inventory and source PDF here.

    Grouping engines:
      - BUCKET_V2: new conservative DocumentBucketResolver
      - LEGACY: existing identity/boundary/group resolver chain
    """

    def __init__(
        self,
        *,
        grouping_engine: str | None = None,
        identity_resolver: DocumentIdentityResolver | None = None,
        boundary_resolver: BoundaryResolver | None = None,
        group_resolver: Any | None = None,
        identity_role_resolver: IdentityRoleResolver | None = None,
        sequence_refiner: DocumentSequenceRefiner | None = None,
        physical_builder: PhysicalDocumentBuilder | None = None,
    ) -> None:
        configured_engine = (
            grouping_engine
            or os.getenv("SWEET_GROUPING_ENGINE")
            or DEFAULT_GROUPING_ENGINE
        )

        self.grouping_engine = configured_engine.strip().upper()

        if self.grouping_engine not in {
            LEGACY_GROUPING_ENGINE,
            BUCKET_GROUPING_ENGINE,
        }:
            raise ValueError(
                "Unsupported SWEET_GROUPING_ENGINE: "
                f"{self.grouping_engine}. "
                f"Allowed values: {LEGACY_GROUPING_ENGINE}, "
                f"{BUCKET_GROUPING_ENGINE}"
            )

        self.identity_resolver = (
            identity_resolver or DocumentIdentityResolver()
        )
        self.boundary_resolver = (
            boundary_resolver or BoundaryResolver()
        )

        if group_resolver is not None:
            self.group_resolver = group_resolver
        elif self.grouping_engine == BUCKET_GROUPING_ENGINE:
            self.group_resolver = DocumentBucketResolver()
        else:
            self.group_resolver = DocumentGroupResolver(
                identity_resolver=self.identity_resolver,
                boundary_resolver=self.boundary_resolver,
            )

        self.identity_role_resolver = (
            identity_role_resolver or IdentityRoleResolver()
        )
        self.sequence_refiner = (
            sequence_refiner or DocumentSequenceRefiner()
        )
        self.physical_builder = (
            physical_builder or PhysicalDocumentBuilder()
        )

    def run(
        self,
        *,
        inventory: Any,
        source_pdf: str | Path,
        output_root: str | Path,
    ) -> ClassifyAndSegregateResult:
        if self.grouping_engine == BUCKET_GROUPING_ENGINE:
            # Semantic refinement changes only page types/evidence.
            # DocumentBucketResolver remains responsible for safe grouping.
            inventory = self.identity_role_resolver.resolve_inventory(
                inventory
            )
            inventory = self.sequence_refiner.resolve_inventory(
                inventory
            )
            group_resolution = self.group_resolver.resolve_inventory(
                inventory
            )
        else:
            identity_decisions = (
                self.identity_resolver.resolve_inventory(
                    inventory
                )
            )

            boundary_decisions = (
                self.boundary_resolver.resolve_inventory(
                    inventory
                )
            )

            group_resolution = (
                self.group_resolver.resolve_inventory(
                    inventory,
                    identity_decisions=identity_decisions,
                    boundary_decisions=boundary_decisions,
                )
            )

        physical_result = self.physical_builder.build(
            source_pdf=source_pdf,
            group_resolution=group_resolution,
            output_root=output_root,
        )

        documents = [
            {
                "groupId": artifact.group_id,
                "documentType": artifact.document_type,
                "documentFamily": artifact.document_family,
                "sourcePages": artifact.source_pages,
                "pageCount": artifact.page_count,
                "confidence": artifact.confidence,
                "status": artifact.status,
                "reviewFlags": artifact.review_flags,
                "fileName": artifact.output_file_name,
                "filePath": artifact.output_path,
            }
            for artifact in physical_result.artifacts
        ]

        return ClassifyAndSegregateResult(
            packet_id=str(inventory.packet_id),
            total_pages=inventory.total_pages,
            group_count=len(group_resolution.groups),
            logical_grouping_integrity_valid=(
                group_resolution.integrity_valid
            ),
            physical_grouping_integrity_valid=(
                physical_result.integrity_valid
            ),
            grouped_manifest_path=(
                physical_result.manifest_path
            ),
            output_directory=(
                physical_result.output_directory
            ),
            documents=documents,
        )


def serialize_classify_and_segregate_result(
    result: ClassifyAndSegregateResult,
) -> dict[str, Any]:
    return {
        "success": True,
        "packetId": result.packet_id,
        "totalPages": result.total_pages,
        "groupCount": result.group_count,
        "logicalGroupingIntegrityValid": (
            result.logical_grouping_integrity_valid
        ),
        "physicalGroupingIntegrityValid": (
            result.physical_grouping_integrity_valid
        ),
        "groupedManifestPath": (
            result.grouped_manifest_path
        ),
        "outputDirectory": result.output_directory,
        "documents": result.documents,
    }


__all__ = [
    "BUCKET_GROUPING_ENGINE",
    "ClassifyAndSegregatePipeline",
    "ClassifyAndSegregateResult",
    "LEGACY_GROUPING_ENGINE",
    "serialize_classify_and_segregate_result",
]
