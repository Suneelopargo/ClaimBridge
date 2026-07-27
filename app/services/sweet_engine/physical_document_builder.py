# app/services/sweet_engine/physical_document_builder.py

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter

from app.services.sweet_engine.document_group_resolver import (
    DocumentGroup,
    DocumentGroupResolution,
)


@dataclass
class PhysicalDocumentArtifact:
    group_id: str
    document_type: str
    document_family: str
    source_pages: list[int]
    output_file_name: str
    output_path: str
    page_count: int
    confidence: float
    status: str
    review_flags: list[str] = field(default_factory=list)


@dataclass
class PhysicalGroupingResult:
    packet_id: str
    source_pdf: str
    output_directory: str
    manifest_path: str
    artifacts: list[PhysicalDocumentArtifact]
    expected_page_count: int
    written_page_count: int
    missing_source_pages: list[int]
    duplicate_source_pages: list[int]
    integrity_valid: bool


class PhysicalDocumentBuilder:
    """
    Create one physical PDF per logical DocumentGroup.

    Source page numbers in DocumentGroup are 1-based.
    pypdf page indexes are 0-based.
    """

    def build(
        self,
        *,
        source_pdf: str | Path,
        group_resolution: DocumentGroupResolution,
        output_root: str | Path,
        clean_output_directory: bool = True,
    ) -> PhysicalGroupingResult:
        source_path = Path(source_pdf).resolve()
        output_root_path = Path(output_root).resolve()

        if not source_path.exists():
            raise FileNotFoundError(
                f"Source PDF not found: {source_path}"
            )

        if source_path.suffix.lower() != ".pdf":
            raise ValueError(
                f"Source file must be PDF: {source_path}"
            )

        if not group_resolution.integrity_valid:
            raise ValueError(
                "Logical grouping integrity is invalid. "
                f"Ungrouped={group_resolution.ungrouped_pages}, "
                f"duplicates={group_resolution.duplicate_pages}"
            )

        packet_output_dir = (
            output_root_path / str(group_resolution.packet_id)
        )

        if clean_output_directory and packet_output_dir.exists():
            shutil.rmtree(packet_output_dir)

        packet_output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        reader = PdfReader(str(source_path))
        source_page_count = len(reader.pages)

        if source_page_count != group_resolution.total_pages:
            raise ValueError(
                "Source PDF page count does not match logical "
                "group resolution. "
                f"PDF={source_page_count}, "
                f"resolution={group_resolution.total_pages}"
            )

        artifacts: list[PhysicalDocumentArtifact] = []
        used_pages: list[int] = []

        for sequence, group in enumerate(
            group_resolution.groups,
            start=1,
        ):
            artifact = self._write_group_pdf(
                reader=reader,
                group=group,
                sequence=sequence,
                output_directory=packet_output_dir,
            )
            artifacts.append(artifact)
            used_pages.extend(group.page_numbers)

        missing_pages, duplicate_pages = (
            self._validate_used_pages(
                total_pages=source_page_count,
                used_pages=used_pages,
            )
        )

        integrity_valid = (
            not missing_pages
            and not duplicate_pages
            and sum(item.page_count for item in artifacts)
            == source_page_count
        )

        manifest_path = (
            packet_output_dir / "grouped_manifest.json"
        )

        result = PhysicalGroupingResult(
            packet_id=str(group_resolution.packet_id),
            source_pdf=str(source_path),
            output_directory=str(packet_output_dir),
            manifest_path=str(manifest_path),
            artifacts=artifacts,
            expected_page_count=source_page_count,
            written_page_count=sum(
                item.page_count
                for item in artifacts
            ),
            missing_source_pages=missing_pages,
            duplicate_source_pages=duplicate_pages,
            integrity_valid=integrity_valid,
        )

        self._write_manifest(
            manifest_path=manifest_path,
            result=result,
        )

        if not integrity_valid:
            raise RuntimeError(
                "Physical grouping integrity failed after PDF "
                "generation. "
                f"Missing={missing_pages}, "
                f"duplicates={duplicate_pages}"
            )

        return result

    def _write_group_pdf(
        self,
        *,
        reader: PdfReader,
        group: DocumentGroup,
        sequence: int,
        output_directory: Path,
    ) -> PhysicalDocumentArtifact:
        writer = PdfWriter()

        for source_page_number in group.page_numbers:
            source_index = source_page_number - 1

            if source_index < 0 or source_index >= len(reader.pages):
                raise IndexError(
                    f"Group {group.group_id} references invalid "
                    f"source page {source_page_number}."
                )

            writer.add_page(reader.pages[source_index])

        safe_type = self._safe_file_component(
            group.document_type
        )
        output_file_name = (
            f"{sequence:03d}_{safe_type}.pdf"
        )
        output_path = (
            output_directory / output_file_name
        )

        with output_path.open("wb") as handle:
            writer.write(handle)

        # Read the output again to verify it was physically written.
        verification_reader = PdfReader(str(output_path))
        written_page_count = len(verification_reader.pages)

        if written_page_count != len(group.page_numbers):
            raise RuntimeError(
                f"Physical PDF verification failed for "
                f"{group.group_id}. Expected "
                f"{len(group.page_numbers)} pages, wrote "
                f"{written_page_count}."
            )

        return PhysicalDocumentArtifact(
            group_id=group.group_id,
            document_type=group.document_type,
            document_family=group.document_family,
            source_pages=list(group.page_numbers),
            output_file_name=output_file_name,
            output_path=str(output_path),
            page_count=written_page_count,
            confidence=group.confidence,
            status=group.status.value,
            review_flags=list(group.review_flags),
        )

    @staticmethod
    def _validate_used_pages(
        *,
        total_pages: int,
        used_pages: list[int],
    ) -> tuple[list[int], list[int]]:
        expected = set(range(1, total_pages + 1))
        actual = set(used_pages)

        missing_pages = sorted(expected - actual)

        counts: dict[int, int] = {}
        for page_number in used_pages:
            counts[page_number] = (
                counts.get(page_number, 0) + 1
            )

        duplicate_pages = sorted(
            page_number
            for page_number, count in counts.items()
            if count > 1
        )

        return missing_pages, duplicate_pages

    @staticmethod
    def _safe_file_component(value: Any) -> str:
        normalized = str(value or "UNKNOWN").strip().upper()
        normalized = re.sub(
            r"[^A-Z0-9]+",
            "_",
            normalized,
        )
        normalized = normalized.strip("_")
        return normalized or "UNKNOWN"

    @staticmethod
    def _write_manifest(
        *,
        manifest_path: Path,
        result: PhysicalGroupingResult,
    ) -> None:
        payload = {
            **asdict(result),
            "artifacts": [
                asdict(item)
                for item in result.artifacts
            ],
        }

        with manifest_path.open(
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                payload,
                handle,
                indent=2,
                ensure_ascii=False,
            )


__all__ = [
    "PhysicalDocumentArtifact",
    "PhysicalDocumentBuilder",
    "PhysicalGroupingResult",
]
