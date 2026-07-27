# app/services/sweet_engine_v2/document_sequence_refiner.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.services.sweet_engine.page_inventory import PageInventory
from app.services.sweet_engine_v2.claim_document_catalog import (
    document_family,
    normalize_document_type,
)


@dataclass(frozen=True)
class SequenceProfile:
    """
    Declarative rules for one multi-page document family.

    New families can be supported by adding another profile; no new
    PharmacyEpisodeResolver, AuthorizationEpisodeResolver, etc. is needed.
    """

    name: str
    anchor_types: frozenset[str]
    continuation_type: str
    ambiguous_types: frozenset[str]
    semantic_terms: tuple[str, ...]
    identifier_keys: tuple[str, ...] = ()
    max_anchor_distance: int = 4
    minimum_semantic_hits: int = 1


DEFAULT_SEQUENCE_PROFILES: tuple[SequenceProfile, ...] = (
    SequenceProfile(
        name="AUTHORIZATION",
        anchor_types=frozenset({
            "CASHLESS_AUTHORIZATION_LETTER",
            "INITIAL_AUTHORIZATION",
            "FINAL_AUTHORIZATION",
            "ENHANCEMENT_REQUEST",
            "ENHANCEMENT_APPROVAL",
            "GOP_PRE_APPROVAL",
            "GOP_FINAL_APPROVAL",
            "APPROVAL_LETTER",
        }),
        continuation_type="AUTHORIZATION_CONTINUATION",
        ambiguous_types=frozenset({
            "AUTHORIZATION_CONTINUATION",
            "BILL_CONTINUATION",
            "FORM_CONTINUATION",
            "DETAILED_BILL",
        }),
        semantic_terms=(
            "authorisation",
            "authorization",
            "deduction details",
            "approved amount",
            "sanctioned amount",
            "non payable",
            "non-payable",
            "co-pay",
            "copay",
            "annexure",
            "terms and conditions",
            "reference number",
            "cashless",
        ),
        identifier_keys=(
            "authorizationNumber",
            "claimNumber",
            "policyNumber",
            "memberId",
        ),
        max_anchor_distance=4,
    ),
    SequenceProfile(
        name="BILL",
        anchor_types=frozenset({
            "FINAL_HOSPITAL_BILL",
            "DETAILED_BILL",
            "BILL_SUMMARY",
        }),
        continuation_type="BILL_CONTINUATION",
        ambiguous_types=frozenset({
            "BILL_CONTINUATION",
            "DETAILED_BILL",
        }),
        semantic_terms=(
            "bill number",
            "tax invoice",
            "hospital bill",
            "charges",
            "payer payable",
            "pharmacy & consumables",
            "professional services",
            "ward",
            "icu",
            "gst details",
            "bed details",
        ),
        identifier_keys=(
            "billNumber",
            "ipNumber",
            "claimNumber",
        ),
        max_anchor_distance=8,
    ),
    SequenceProfile(
        name="PHARMACY",
        anchor_types=frozenset({
            "PHARMACY_BILL",
            "MEDICINE_INVOICE",
            "PHARMACY_REPORT",
        }),
        continuation_type="PHARMACY_BILL",
        ambiguous_types=frozenset({
            "BILL_CONTINUATION",
            "PHARMACY_BILL",
            "MEDICINE_INVOICE",
            "PHARMACY_REPORT",
        }),
        semantic_terms=(
            "pharmacy",
            "medicine",
            "drug",
            "batch no",
            "batch number",
            "quantity",
            "expiry",
            "mrp",
            "dispensed",
            "prescription",
        ),
        identifier_keys=(
            "billNumber",
            "invoiceNumber",
            "prescriptionNumber",
            "ipNumber",
        ),
        max_anchor_distance=5,
    ),
)


class DocumentSequenceRefiner:
    """
    Generic semantic refinement for multi-page document sequences.

    It operates before DocumentBucketResolver. It does not directly merge
    pages. It only corrects an ambiguous continuation page's canonical type
    when a nearby anchor, semantic evidence and identifier evidence support
    one document family.

    The normal bucket resolver remains responsible for the final safe merge.
    """

    def __init__(
        self,
        profiles: Iterable[SequenceProfile] | None = None,
    ) -> None:
        self.profiles = tuple(
            profiles or DEFAULT_SEQUENCE_PROFILES
        )

    def resolve_inventory(
        self,
        inventory: PageInventory,
    ) -> PageInventory:
        pages = sorted(
            inventory.pages,
            key=lambda item: item.page_number,
        )

        for page in pages:
            candidates = [
                decision
                for profile in self.profiles
                if (
                    decision := self._evaluate_profile(
                        page=page,
                        pages=pages,
                        profile=profile,
                    )
                ) is not None
            ]

            if not candidates:
                continue

            candidates.sort(
                key=lambda item: item["score"],
                reverse=True,
            )

            best = candidates[0]

            # Avoid changing a page when two families have nearly equal support.
            if (
                len(candidates) > 1
                and candidates[0]["score"] - candidates[1]["score"] < 20
            ):
                page.add_processing_note(
                    "Document sequence refinement was not applied because "
                    "multiple document families had similar evidence."
                )
                continue

            original_type = normalize_document_type(
                page.final_document_type
            )
            refined_type = best["continuation_type"]

            if original_type == refined_type:
                continue

            page.final_document_type = refined_type
            page.evidence.custom_features[
                "sequenceRefinement"
            ] = {
                "profile": best["profile"],
                "originalDocumentType": original_type,
                "refinedDocumentType": refined_type,
                "score": best["score"],
                "anchorPage": best["anchor_page"],
                "reasons": best["reasons"],
            }
            page.add_processing_note(
                f"Sequence refinement changed {original_type} to "
                f"{refined_type}; profile={best['profile']}, "
                f"anchor page={best['anchor_page']}, "
                f"score={best['score']}."
            )

        return inventory

    def _evaluate_profile(
        self,
        *,
        page,
        pages,
        profile: SequenceProfile,
    ) -> dict | None:
        page_type = normalize_document_type(
            page.final_document_type
        )

        if page_type not in profile.ambiguous_types:
            return None

        # Do not rewrite a clear explicit document start into a continuation.
        if self._bool_feature(page, "explicitDocumentStart"):
            return None

        nearest_anchor = self._nearest_anchor(
            page=page,
            pages=pages,
            profile=profile,
        )

        if nearest_anchor is None:
            return None

        anchor, distance = nearest_anchor
        semantic_hits = self._semantic_hits(
            page=page,
            terms=profile.semantic_terms,
        )
        identifier_matches = self._identifier_matches(
            page=page,
            anchor=anchor,
            keys=profile.identifier_keys,
        )
        identifier_conflicts = self._identifier_conflicts(
            page=page,
            anchor=anchor,
            keys=profile.identifier_keys,
        )

        if identifier_conflicts:
            return None

        # Require semantic evidence unless a strong shared identifier exists.
        if (
            len(semantic_hits) < profile.minimum_semantic_hits
            and not identifier_matches
        ):
            return None

        score = 0
        reasons: list[str] = []

        adjacency_score = max(
            0,
            35 - ((distance - 1) * 8),
        )
        score += adjacency_score
        reasons.append(
            f"Nearby {profile.name} anchor at page "
            f"{anchor.page_number} (distance {distance})."
        )

        if semantic_hits:
            semantic_score = min(45, len(semantic_hits) * 12)
            score += semantic_score
            reasons.append(
                "Semantic evidence: " + ", ".join(semantic_hits[:5])
            )

        if identifier_matches:
            identifier_score = min(
                70,
                len(identifier_matches) * 35,
            )
            score += identifier_score
            reasons.append(
                "Matching identifiers: "
                + ", ".join(identifier_matches)
            )

        page_role = str(
            self._feature(page, "pageRole") or ""
        ).upper()

        if page_role in {"CONTINUATION", "END"}:
            score += 20
            reasons.append(f"Page role is {page_role}.")

        if self._bool_feature(page, "explicitDocumentEnd"):
            score += 10
            reasons.append("Page explicitly closes a document.")

        # Require enough combined evidence to refine the canonical type.
        if score < 55:
            return None

        return {
            "profile": profile.name,
            "continuation_type": profile.continuation_type,
            "score": score,
            "anchor_page": anchor.page_number,
            "reasons": reasons,
        }

    def _nearest_anchor(
        self,
        *,
        page,
        pages,
        profile: SequenceProfile,
    ):
        possible = []

        for candidate in pages:
            candidate_type = normalize_document_type(
                candidate.final_document_type
            )

            if candidate_type not in profile.anchor_types:
                continue

            distance = abs(candidate.page_number - page.page_number)

            if distance == 0 or distance > profile.max_anchor_distance:
                continue

            possible.append((candidate, distance))

        if not possible:
            return None

        possible.sort(
            key=lambda item: (
                item[1],
                0 if item[0].page_number < page.page_number else 1,
            )
        )
        return possible[0]

    def _semantic_hits(
        self,
        *,
        page,
        terms: tuple[str, ...],
    ) -> list[str]:
        haystack = " ".join(
            str(value or "")
            for value in (
                self._feature(page, "visibleTitle"),
                self._feature(page, "sectionTitle"),
                self._feature(page, "templateHint"),
                self._feature(page, "headerSignature"),
                self._feature(page, "footerSignature"),
                self._feature(page, "reason"),
                " ".join(
                    self._list_feature(
                        page,
                        "continuationIndicators",
                    )
                ),
            )
        ).lower()

        return [
            term
            for term in terms
            if term.lower() in haystack
        ]

    def _identifier_matches(
        self,
        *,
        page,
        anchor,
        keys: tuple[str, ...],
    ) -> list[str]:
        matches: list[str] = []

        for key in keys:
            page_value = self._normalise(
                self._feature(page, key)
            )
            anchor_value = self._normalise(
                self._feature(anchor, key)
            )

            if page_value and anchor_value and page_value == anchor_value:
                matches.append(key)

            # Some insurer annexures put the authorization/claim reference
            # only inside the header signature.
            if not page_value:
                header = self._normalise(
                    self._feature(page, "headerSignature")
                )
                if anchor_value and anchor_value in header:
                    matches.append(key)

        return sorted(set(matches))

    def _identifier_conflicts(
        self,
        *,
        page,
        anchor,
        keys: tuple[str, ...],
    ) -> list[str]:
        conflicts: list[str] = []

        for key in keys:
            page_value = self._normalise(
                self._feature(page, key)
            )
            anchor_value = self._normalise(
                self._feature(anchor, key)
            )

            if (
                page_value
                and anchor_value
                and page_value != anchor_value
            ):
                conflicts.append(key)

        return conflicts

    @classmethod
    def _feature(cls, page, key: str):
        snake = cls._camel_to_snake(key)

        for candidate in (key, snake):
            value = getattr(page, candidate, None)
            if value not in (None, ""):
                return value

        identifier_aliases = {
            "patientName": "patient_name",
            "claimNumber": "claim_number",
            "mrn": "mrn",
            "ipNumber": "ip_number",
            "payerName": "payer_name",
            "billNumber": "bill_number",
        }

        if key in identifier_aliases:
            value = getattr(
                page.identifiers,
                identifier_aliases[key],
                None,
            )
            if value not in (None, ""):
                return value

        custom = getattr(
            page.evidence,
            "custom_features",
            {},
        ) or {}

        for candidate in (
            key,
            snake,
            key[0].lower() + key[1:] if key else key,
        ):
            value = custom.get(candidate)
            if value not in (None, ""):
                return value

        return None

    @classmethod
    def _bool_feature(cls, page, key: str) -> bool:
        value = cls._feature(page, key)

        if isinstance(value, bool):
            return value

        return str(value or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
        }

    @classmethod
    def _list_feature(cls, page, key: str) -> list[str]:
        value = cls._feature(page, key)

        if isinstance(value, list):
            return [str(item) for item in value]

        if value in (None, ""):
            return []

        return [str(value)]

    @staticmethod
    def _normalise(value) -> str:
        return "".join(
            character
            for character in str(value or "").upper()
            if character.isalnum()
        )

    @staticmethod
    def _camel_to_snake(value: str) -> str:
        output: list[str] = []

        for character in value:
            if character.isupper():
                output.extend(("_", character.lower()))
            else:
                output.append(character)

        return "".join(output).lstrip("_")


__all__ = [
    "DEFAULT_SEQUENCE_PROFILES",
    "DocumentSequenceRefiner",
    "SequenceProfile",
]
