# scripts/evaluate_document_groups.py

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.services.sweet_engine.adapters.hcg_packet_adapter import (
    build_inventory_from_packet_manifest,
)
from app.services.sweet_engine.boundary_resolver import BoundaryResolver
from app.services.sweet_engine.document_group_resolver import (
    DocumentGroupResolver,
)
from app.services.sweet_engine.document_identity_resolver import (
    DocumentIdentityResolver,
)


DEFAULT_OUTPUT_DIR = Path(
    "data/sweet_evaluation/groups"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate final logical document groups for a SWEET "
            "packet manifest."
        )
    )

    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to manifest.json.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Print reasons and review flags for each group.",
    )
    parser.add_argument(
        "--review-only",
        action="store_true",
        help="Print details only for groups requiring review.",
    )

    return parser.parse_args()


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    if not isinstance(manifest, dict):
        raise ValueError("Manifest root must be a JSON object.")

    return manifest


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest)

    try:
        manifest = load_manifest(manifest_path)

        inventory = build_inventory_from_packet_manifest(
            manifest,
            run_context_resolution=True,
        )

        identity_decisions = (
            DocumentIdentityResolver().resolve_inventory(
                inventory
            )
        )
        boundary_decisions = (
            BoundaryResolver().resolve_inventory(
                inventory
            )
        )

        resolution = DocumentGroupResolver().resolve_inventory(
            inventory,
            identity_decisions=identity_decisions,
            boundary_decisions=boundary_decisions,
        )

        print()
        print("=" * 126)
        print("SWEET Document Group Evaluation")
        print("=" * 126)
        print(f"Packet ID : {resolution.packet_id}")
        print(f"Pages     : {resolution.total_pages}")
        print(f"Groups    : {len(resolution.groups)}")
        print()

        print("-" * 126)
        print(
            f"{'Group':<30}"
            f"{'Document type':<34}"
            f"{'Pages':<20}"
            f"{'Count':>7}"
            f"{'Confidence':>13}"
            f"{'Status':>15}"
        )
        print("-" * 126)

        for group in resolution.groups:
            page_display = ",".join(
                str(number)
                for number in group.page_numbers
            )

            print(
                f"{group.group_id:<30}"
                f"{group.document_type[:32]:<34}"
                f"{page_display[:18]:<20}"
                f"{group.page_count:>7}"
                f"{group.confidence:>13.2f}"
                f"{group.status.value:>15}"
            )

        print("-" * 126)

        if args.details or args.review_only:
            for group in resolution.groups:
                if (
                    args.review_only
                    and group.status.value != "REVIEW"
                ):
                    continue

                print()
                print("=" * 92)
                print(
                    f"{group.group_id} — "
                    f"{group.document_type}"
                )
                print("=" * 92)
                print(
                    f"Pages      : {group.page_numbers}"
                )
                print(
                    f"Family     : {group.document_family}"
                )
                print(
                    f"Confidence : {group.confidence:.2f}"
                )
                print(
                    f"Status     : {group.status.value}"
                )
                print(
                    f"Chains     : "
                    f"{group.identity_chain_ids}"
                )

                if group.reasons:
                    print("Reasons:")
                    for reason in group.reasons:
                        print(f"  - {reason}")

                if group.review_flags:
                    print("Review flags:")
                    for flag in group.review_flags:
                        print(f"  ! {flag}")

        print()
        print("Grouping integrity")
        print("-" * 60)
        print(
            f"groupedPages: {resolution.grouped_pages}"
        )
        print(
            f"ungroupedPages: {resolution.ungrouped_pages}"
        )
        print(
            f"duplicatePages: {resolution.duplicate_pages}"
        )
        print(
            f"integrityValid: {resolution.integrity_valid}"
        )

        output_dir = Path(args.output_dir)
        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path = output_dir / (
            f"{resolution.packet_id}-groups.json"
        )

        report = {
            "packetId": resolution.packet_id,
            "totalPages": resolution.total_pages,
            "groupCount": len(resolution.groups),
            "groupedPages": resolution.grouped_pages,
            "ungroupedPages": resolution.ungrouped_pages,
            "duplicatePages": resolution.duplicate_pages,
            "integrityValid": resolution.integrity_valid,
            "groups": [
                {
                    **asdict(group),
                    "status": group.status.value,
                    "pageCount": group.page_count,
                }
                for group in resolution.groups
            ],
        }

        with output_path.open(
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                report,
                handle,
                indent=2,
                ensure_ascii=False,
            )

        print()
        print(f"Group JSON: {output_path.resolve()}")
        return 0

    except Exception as exc:
        print(
            f"Group evaluation failed: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
