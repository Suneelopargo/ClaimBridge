# scripts/build_physical_documents.py

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.services.sweet_engine.adapters.hcg_packet_adapter import (
    build_inventory_from_packet_manifest,
)
from app.services.sweet_engine.classify_and_segregate_pipeline import (
    ClassifyAndSegregatePipeline,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run logical and physical grouping for an HCG packet."
        )
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to the packet manifest.json.",
    )
    parser.add_argument(
        "--source-pdf",
        required=True,
        help="Path to the original unsplit HCG PDF.",
    )
    parser.add_argument(
        "--output-root",
        default="data/sweet_grouped",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        manifest_path = Path(args.manifest)
        with manifest_path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            manifest = json.load(handle)

        inventory = build_inventory_from_packet_manifest(
            manifest,
            run_context_resolution=True,
        )

        result = ClassifyAndSegregatePipeline().run(
            inventory=inventory,
            source_pdf=args.source_pdf,
            output_root=args.output_root,
        )

        print()
        print("=" * 90)
        print("SWEET Physical Document Grouping")
        print("=" * 90)
        print(f"Packet ID : {result.packet_id}")
        print(f"Pages     : {result.total_pages}")
        print(f"Groups    : {result.group_count}")
        print(
            "Logical integrity : "
            f"{result.logical_grouping_integrity_valid}"
        )
        print(
            "Physical integrity: "
            f"{result.physical_grouping_integrity_valid}"
        )
        print()

        for document in result.documents:
            print(
                f"{document['fileName']:<42} "
                f"pages={document['sourcePages']} "
                f"status={document['status']}"
            )

        print()
        print(
            f"Output directory: {result.output_directory}"
        )
        print(
            f"Grouped manifest: "
            f"{result.grouped_manifest_path}"
        )
        return 0

    except Exception as exc:
        print(
            f"Physical grouping failed: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
