# scripts/evaluate_document_boundaries.py

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.services.sweet_engine.adapters.hcg_packet_adapter import (
    build_inventory_from_packet_manifest,
)
from app.services.sweet_engine.boundary_resolver import (
    BoundaryDecision,
    BoundaryResolver,
)


DEFAULT_OUTPUT_DIR = Path("data/sweet_evaluation/boundaries")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate document boundaries for a ClaimsBridge/HCG packet "
            "manifest without modifying the production manifest or creating "
            "grouped PDFs."
        )
    )

    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to the packet manifest.json file.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=(
            "Directory where the boundary evaluation JSON will be written. "
            f"Default: {DEFAULT_OUTPUT_DIR}"
        ),
    )
    parser.add_argument(
        "--no-context",
        action="store_true",
        help=(
            "Skip ContextResolver while building the PageInventory. "
            "EvidenceResolver still runs through the HCG adapter."
        ),
    )
    parser.add_argument(
        "--minimum-vision-confidence",
        type=float,
        default=0.70,
        help="Minimum Vision confidence used by PageInventory. Default: 0.70",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Print detailed signals for every page.",
    )
    parser.add_argument(
        "--ambiguous-only",
        action="store_true",
        help=(
            "Print detailed signals only for AMBIGUOUS boundaries. "
            "The summary table is always printed."
        ),
    )

    return parser.parse_args()


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest does not exist: {manifest_path}")
    if not manifest_path.is_file():
        raise ValueError(f"Manifest path is not a file: {manifest_path}")

    try:
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Manifest is not valid JSON: {manifest_path}") from exc

    if not isinstance(manifest, dict):
        raise ValueError("Manifest root must be a JSON object.")

    return manifest


def decision_to_dict(
    decision: BoundaryDecision,
    page: Any,
) -> dict[str, Any]:
    return {
        "pageNumber": decision.page_number,
        "finalDocumentType": str(page.final_document_type or "UNKNOWN"),
        "rawDocumentType": str(page.raw_document_type or "UNKNOWN"),
        "boundaryType": decision.boundary_type.value,
        "score": decision.score,
        "confidence": round(float(decision.confidence), 4),
        "reviewRequired": bool(getattr(page.review, "required", False)),
        "reasons": list(decision.reasons),
        "signals": [
            {
                "code": signal.code,
                "direction": signal.direction,
                "weight": signal.weight,
                "score": (
                 signal.weight
                 if signal.direction == "START"
                 else -signal.weight
                 ),
                "reason": signal.reason,
            }
            for signal in decision.signals
        ],
    }


def build_report(
    *,
    manifest_path: Path,
    inventory: Any,
    decisions: list[BoundaryDecision],
) -> dict[str, Any]:
    pages_by_number = {page.page_number: page for page in inventory.pages}
    boundary_counts: dict[str, int] = {}
    page_results: list[dict[str, Any]] = []

    for decision in decisions:
        boundary_name = decision.boundary_type.value
        boundary_counts[boundary_name] = boundary_counts.get(boundary_name, 0) + 1
        page_results.append(
            decision_to_dict(decision, pages_by_number[decision.page_number])
        )

    ambiguous_pages = [
        item["pageNumber"]
        for item in page_results
        if item["boundaryType"] == "AMBIGUOUS"
    ]
    start_pages = [
        item["pageNumber"]
        for item in page_results
        if item["boundaryType"] == "START"
    ]
    continuation_pages = [
        item["pageNumber"]
        for item in page_results
        if item["boundaryType"] == "CONTINUATION"
    ]

    return {
        "packetId": inventory.packet_id,
        "manifestPath": str(manifest_path),
        "totalPages": inventory.total_pages,
        "inventoryPages": len(inventory.pages),
        "boundaryCounts": boundary_counts,
        "startPages": start_pages,
        "continuationPages": continuation_pages,
        "ambiguousPages": ambiguous_pages,
        "ambiguousPageCount": len(ambiguous_pages),
        "droppedPages": inventory.total_pages - len(inventory.pages),
        "pageIntegrityValid": inventory.total_pages == len(inventory.pages),
        "pages": page_results,
    }


def print_summary(
    *,
    inventory: Any,
    decisions: list[BoundaryDecision],
) -> None:
    pages_by_number = {page.page_number: page for page in inventory.pages}

    print()
    print("=" * 118)
    print("SWEET Document Boundary Evaluation")
    print("=" * 118)
    print(f"Packet ID : {inventory.packet_id}")
    print(f"Pages     : {inventory.total_pages}")
    print()

    print("-" * 118)
    print(
        f"{'Pg':<5}"
        f"{'Raw type':<32}"
        f"{'Final type':<34}"
        f"{'Boundary':<16}"
        f"{'Score':>8}"
        f"{'Confidence':>13}"
    )
    print("-" * 118)

    for decision in decisions:
        page = pages_by_number[decision.page_number]
        raw_type = str(page.raw_document_type or "UNKNOWN")
        final_type = str(page.final_document_type or "UNKNOWN")

        print(
            f"{decision.page_number:<5}"
            f"{truncate(raw_type, 30):<32}"
            f"{truncate(final_type, 32):<34}"
            f"{decision.boundary_type.value:<16}"
            f"{decision.score:>8}"
            f"{decision.confidence:>13.2f}"
        )

    print("-" * 118)


def print_detailed_decisions(
    *,
    inventory: Any,
    decisions: list[BoundaryDecision],
    ambiguous_only: bool,
) -> None:
    pages_by_number = {page.page_number: page for page in inventory.pages}

    for decision in decisions:
        if ambiguous_only and decision.boundary_type.value != "AMBIGUOUS":
            continue

        page = pages_by_number[decision.page_number]

        print()
        print("=" * 86)
        print(f"Page {decision.page_number} — {page.final_document_type}")
        print("=" * 86)
        print(f"Boundary   : {decision.boundary_type.value}")
        print(f"Score      : {decision.score}")
        print(f"Confidence : {decision.confidence:.2f}")

        if not decision.signals:
            print("Signals    : None")
            continue

        print("Signals:")
        for signal in decision.signals:
            display_weight = (
                signal.weight
                if signal.direction == "START"
                else -signal.weight
            )

            sign = "+" if display_weight >= 0 else ""

            print(
                f"  {sign}{display_weight:<4} "
                f"{signal.code:<32} "
                f"{signal.reason}"
            )


def print_report_summary(report: dict[str, Any], output_path: Path) -> None:
    print()
    print("Boundary evaluation summary")
    print("-" * 60)
    print(f"packetId: {report['packetId']}")
    print(f"totalPages: {report['totalPages']}")
    print(f"inventoryPages: {report['inventoryPages']}")
    print(f"boundaryCounts: {report['boundaryCounts']}")
    print(f"ambiguousPages: {report['ambiguousPages']}")
    print(f"droppedPages: {report['droppedPages']}")
    print(f"pageIntegrityValid: {report['pageIntegrityValid']}")
    print()
    print(f"Boundary JSON: {output_path.resolve()}")


def truncate(value: str, maximum_length: int) -> str:
    if len(value) <= maximum_length:
        return value
    return value[: maximum_length - 3] + "..."


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest)

    try:
        manifest = load_manifest(manifest_path)

        inventory = build_inventory_from_packet_manifest(
            manifest,
            run_context_resolution=not args.no_context,
            minimum_vision_confidence=args.minimum_vision_confidence,
        )

        decisions = BoundaryResolver().resolve_inventory(inventory)
        inventory.assert_no_page_drop()

        print_summary(inventory=inventory, decisions=decisions)

        if args.details or args.ambiguous_only:
            print_detailed_decisions(
                inventory=inventory,
                decisions=decisions,
                ambiguous_only=args.ambiguous_only,
            )

        report = build_report(
            manifest_path=manifest_path,
            inventory=inventory,
            decisions=decisions,
        )

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{inventory.packet_id}-boundaries.json"

        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)

        print_report_summary(report, output_path)
        return 0

    except Exception as exc:
        print(f"Boundary evaluation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
