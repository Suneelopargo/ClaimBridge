# scripts/evaluate_document_identities.py

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.services.sweet_engine.adapters.hcg_packet_adapter import build_inventory_from_packet_manifest
from app.services.sweet_engine.document_identity_resolver import DocumentIdentityResolver

DEFAULT_OUTPUT_DIR = Path("data/sweet_evaluation/identities")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate provisional document identities for a packet manifest.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--uncertain-only", action="store_true")
    return parser.parse_args()


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict):
        raise ValueError("Manifest root must be a JSON object.")
    return manifest


def signed_weight(signal: Any) -> int:
    return signal.weight if signal.direction == "NEW_DOCUMENT" else -signal.weight


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest)

    try:
        inventory = build_inventory_from_packet_manifest(
            load_manifest(manifest_path),
            run_context_resolution=True,
        )
        decisions = DocumentIdentityResolver().resolve_inventory(inventory)
        pages_by_number = {page.page_number: page for page in inventory.pages}

        print()
        print("=" * 126)
        print("SWEET Document Identity Evaluation")
        print("=" * 126)
        print(f"Packet ID : {inventory.packet_id}")
        print(f"Pages     : {inventory.total_pages}")
        print()
        print("-" * 126)
        print(
            f"{'Pg':<5}{'Final type':<34}{'Relation':<19}"
            f"{'Same':>8}{'New':>8}{'Net':>8}{'Confidence':>13}"
            f"{'Identity chain':>24}"
        )
        print("-" * 126)

        for decision in decisions:
            final_type = str(pages_by_number[decision.page_number].final_document_type or "UNKNOWN")
            print(
                f"{decision.page_number:<5}{final_type[:32]:<34}"
                f"{decision.relation.value:<19}{decision.same_document_score:>8}"
                f"{decision.new_document_score:>8}{decision.net_score:>8}"
                f"{decision.confidence:>13.2f}{str(decision.identity_chain_id):>24}"
            )

        print("-" * 126)

        if args.details or args.uncertain_only:
            for decision in decisions:
                if args.uncertain_only and decision.relation.value != "UNCERTAIN":
                    continue
                page = pages_by_number[decision.page_number]
                print()
                print("=" * 90)
                print(f"Page {decision.page_number} — {page.final_document_type}")
                print("=" * 90)
                print(f"Relation   : {decision.relation.value}")
                print(f"Same score : {decision.same_document_score}")
                print(f"New score  : {decision.new_document_score}")
                print(f"Net score  : {decision.net_score}")
                print(f"Confidence : {decision.confidence:.2f}")
                print(f"Chain      : {decision.identity_chain_id}")
                print("Signals:")
                for signal in decision.signals:
                    value = signed_weight(signal)
                    sign = "+" if value >= 0 else ""
                    print(f"  {sign}{value:<4} {signal.code:<34} {signal.reason}")

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{inventory.packet_id}-identities.json"

        report = {
            "packetId": inventory.packet_id,
            "totalPages": inventory.total_pages,
            "identityChains": sorted({d.identity_chain_id for d in decisions if d.identity_chain_id}),
            "uncertainPages": [d.page_number for d in decisions if d.relation.value == "UNCERTAIN"],
            "pages": [
                {
                    "pageNumber": d.page_number,
                    "previousPageNumber": d.previous_page_number,
                    "relation": d.relation.value,
                    "sameDocumentScore": d.same_document_score,
                    "newDocumentScore": d.new_document_score,
                    "netScore": d.net_score,
                    "confidence": d.confidence,
                    "identityChainId": d.identity_chain_id,
                    "fingerprint": asdict(d.fingerprint),
                    "signals": [asdict(signal) for signal in d.signals],
                }
                for d in decisions
            ],
        }

        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)

        print()
        print(f"Identity JSON: {output_path.resolve()}")
        return 0
    except Exception as exc:
        print(f"Identity evaluation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
