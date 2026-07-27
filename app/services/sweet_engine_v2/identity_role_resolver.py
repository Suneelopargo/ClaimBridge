# app/services/sweet_engine_v2/identity_role_resolver.py

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from app.services.sweet_engine.page_inventory import PageInventory
from app.services.sweet_engine_v2.claim_document_catalog import (
    normalize_document_type,
)


class IdentityRoleResolver:
    """
    Refine identity-document roles before logical grouping.

    This resolver does not merge identity pages. It only changes the semantic
    document type when the name printed on an ID clearly matches, or clearly
    does not match, the packet patient.

    Conservative policy:
      * patient-name match -> PATIENT_ID_PROOF
      * clear different person -> PROPOSER_ID_PROOF
      * missing/unreadable name -> retain current type and add a note
    """

    IDENTITY_TYPES = {
        "PATIENT_ID_PROOF",
        "PROPOSER_ID_PROOF",
        "ATTENDANT_ID_PROOF",
    }

    MATCH_THRESHOLD = 0.86
    MISMATCH_THRESHOLD = 0.58

    def resolve_inventory(
        self,
        inventory: PageInventory,
    ) -> PageInventory:
        packet_patient_name = self._packet_patient_name(inventory)

        if not packet_patient_name:
            return inventory

        for page in inventory.pages:
            page_type = normalize_document_type(page.final_document_type)

            if page_type not in self.IDENTITY_TYPES:
                continue

            printed_name = self._page_person_name(page)

            if not printed_name:
                page.add_processing_note(
                    "Identity role could not be refined because no readable "
                    "person name was extracted from the ID page."
                )
                continue

            similarity = self._name_similarity(
                printed_name,
                packet_patient_name,
            )

            custom = page.evidence.custom_features
            custom["identityRoleResolution"] = {
                "packetPatientName": packet_patient_name,
                "printedPersonName": printed_name,
                "nameSimilarity": round(similarity, 4),
            }

            if similarity >= self.MATCH_THRESHOLD:
                page.final_document_type = "PATIENT_ID_PROOF"
                page.add_processing_note(
                    "Identity role refined to PATIENT_ID_PROOF because the "
                    f"printed name '{printed_name}' matches packet patient "
                    f"'{packet_patient_name}' ({similarity:.2f})."
                )
                continue

            if similarity <= self.MISMATCH_THRESHOLD:
                page.final_document_type = "PROPOSER_ID_PROOF"
                page.add_processing_note(
                    "Identity role refined to PROPOSER_ID_PROOF because the "
                    f"printed name '{printed_name}' is clearly different from "
                    f"packet patient '{packet_patient_name}' "
                    f"({similarity:.2f})."
                )
                continue

            page.add_processing_note(
                "Identity role remains unchanged because the name comparison "
                f"was inconclusive ({similarity:.2f})."
            )

        return inventory

    def _packet_patient_name(
        self,
        inventory: PageInventory,
    ) -> str:
        explicit = str(
            getattr(inventory, "packet_patient_name", "") or ""
        ).strip()

        if explicit:
            return explicit

        # Fallback: choose the most frequent patient name found on strong
        # hospital/claim documents, excluding identity documents.
        candidates: list[str] = []

        for page in inventory.pages:
            page_type = normalize_document_type(page.final_document_type)

            if page_type in self.IDENTITY_TYPES:
                continue

            name = str(
                getattr(page.identifiers, "patient_name", "") or ""
            ).strip()

            if name:
                candidates.append(name)

        if not candidates:
            return ""

        normalized_counts: dict[str, tuple[str, int]] = {}

        for name in candidates:
            key = self._normalise_name(name)
            original, count = normalized_counts.get(key, (name, 0))
            normalized_counts[key] = (original, count + 1)

        return max(
            normalized_counts.values(),
            key=lambda item: item[1],
        )[0]

    @staticmethod
    def _page_person_name(page: Any) -> str:
        name = str(
            getattr(page.identifiers, "patient_name", "") or ""
        ).strip()

        if name:
            return name

        custom = getattr(page.evidence, "custom_features", {}) or {}

        for key in (
            "personName",
            "idHolderName",
            "printedPersonName",
            "patientName",
        ):
            value = str(custom.get(key) or "").strip()

            if value:
                return value

        return ""

    @classmethod
    def _name_similarity(
        cls,
        left: str,
        right: str,
    ) -> float:
        left_normalized = cls._normalise_name(left)
        right_normalized = cls._normalise_name(right)

        if not left_normalized or not right_normalized:
            return 0.0

        if left_normalized == right_normalized:
            return 1.0

        left_tokens = set(left_normalized.split())
        right_tokens = set(right_normalized.split())

        token_score = (
            len(left_tokens & right_tokens)
            / max(len(left_tokens), len(right_tokens))
        )

        sequence_score = SequenceMatcher(
            None,
            left_normalized,
            right_normalized,
        ).ratio()

        return max(token_score, sequence_score)

    @staticmethod
    def _normalise_name(value: str) -> str:
        cleaned = re.sub(
            r"\b(?:MR|MRS|MS|MISS|DR|SHRI|SMT)\b",
            " ",
            str(value or "").upper(),
        )
        cleaned = re.sub(r"[^A-Z0-9]+", " ", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()


__all__ = ["IdentityRoleResolver"]
