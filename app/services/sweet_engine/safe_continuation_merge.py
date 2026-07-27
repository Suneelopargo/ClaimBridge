# app/services/sweet_engine/safe_continuation_merge.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.sweet_engine.document_registry import (
    document_family,
    normalize_document_type,
)
from app.services.sweet_engine.models import PageInventoryItem


@dataclass(frozen=True)
class ContinuationMergeDecision:
    should_merge: bool
    confidence: float
    reasons: list[str] = field(default_factory=list)


class SafeContinuationMerge:
    """Conservatively attach continuation groups to a preceding anchor.

    A merge is allowed only when:
    - the current group begins with a recognized continuation type;
    - the previous group has a compatible non-continuation anchor;
    - no explicit new-document start exists on the continuation page; and
    - at least one strong continuity signal or two medium signals exist.
    """

    CONTINUATION_TYPES = {
        "BILL_CONTINUATION",
        "AUTHORIZATION_CONTINUATION",
        "FORM_CONTINUATION",
        "DISCHARGE_SUMMARY_CONTINUATION",
        "DOCUMENT_CONTINUATION",
        "CONTINUATION",
    }

    ANCHOR_FOR_CONTINUATION = {
        "BILL_CONTINUATION": {
            "FINAL_HOSPITAL_BILL",
            "DETAILED_BILL_BREAKUP",
        },
        "AUTHORIZATION_CONTINUATION": {
            "CASHLESS_AUTHORIZATION_LETTER",
            "APPROVAL_LETTER",
            "GOP_PRE_APPROVAL",
            "GOP_FINAL_APPROVAL",
        },
        "FORM_CONTINUATION": {
            "PREAUTHORIZATION_FORM",
            "CLAIM_FORM",
            "CONSENT_FORM",
        },
        "DISCHARGE_SUMMARY_CONTINUATION": {
            "DISCHARGE_SUMMARY",
        },
        "DOCUMENT_CONTINUATION": set(),
        "CONTINUATION": set(),
    }

    STRONG_IDENTIFIER_KEYS = (
        "billNumber",
        "authorizationNumber",
        "claimNumber",
        "mrn",
        "ipNumber",
    )

    def decide(
        self,
        *,
        previous_pages: list[PageInventoryItem],
        current_pages: list[PageInventoryItem],
        previous_document_type: str,
        current_document_type: str,
    ) -> ContinuationMergeDecision:
        if not previous_pages or not current_pages:
            return ContinuationMergeDecision(False, 0.0, ["Empty group."])

        previous_type = normalize_document_type(previous_document_type)
        current_type = normalize_document_type(current_document_type)
        first_current = current_pages[0]
        last_previous = previous_pages[-1]

        if current_type not in self.CONTINUATION_TYPES:
            return ContinuationMergeDecision(
                False,
                0.0,
                [f"{current_type} is not a continuation type."],
            )

        if self._bool_feature(first_current, "explicitDocumentStart"):
            return ContinuationMergeDecision(
                False,
                1.0,
                ["Continuation page has an explicit new-document start."],
            )

        if not self._anchor_compatible(previous_type, current_type):
            return ContinuationMergeDecision(
                False,
                1.0,
                [
                    f"Anchor {previous_type} is incompatible with "
                    f"continuation {current_type}."
                ],
            )

        reasons: list[str] = []
        strong_score = 0
        medium_score = 0

        # Strong signal 1: consecutive printed sequence.
        if self._is_consecutive_printed_sequence(last_previous, first_current):
            strong_score += 1
            reasons.append("Consecutive printed page sequence.")

        # Strong signal 2: a document-specific identifier matches.
        matching_identifiers = [
            key
            for key in self.STRONG_IDENTIFIER_KEYS
            if self._same_nonempty_identifier(last_previous, first_current, key)
        ]
        if matching_identifiers:
            strong_score += 1
            reasons.append(
                "Matching identifiers: " + ", ".join(matching_identifiers) + "."
            )

        # Medium signal 1: same normalized template/header/footer signature.
        if self._same_nonempty_text(last_previous, first_current, "templateHint"):
            medium_score += 1
            reasons.append("Matching template hint.")

        if self._same_nonempty_text(last_previous, first_current, "headerSignature"):
            medium_score += 1
            reasons.append("Matching header signature.")

        if self._same_nonempty_text(last_previous, first_current, "footerSignature"):
            medium_score += 1
            reasons.append("Matching footer signature.")

        # Medium signal 2: same patient plus same family.
        if self._same_nonempty_text(last_previous, first_current, "patientName"):
            medium_score += 1
            reasons.append("Matching patient name.")

        if document_family(previous_type) == document_family(current_type):
            medium_score += 1
            reasons.append("Compatible document family.")

        # Medium signal 3: Vision explicitly says continuation/end.
        page_role = str(self._feature(first_current, "pageRole") or "").upper()
        if page_role in {"CONTINUATION", "END"}:
            medium_score += 1
            reasons.append(f"Current page role is {page_role}.")

        continuation_indicators = self._feature(
            first_current,
            "continuationIndicators",
        )
        if isinstance(continuation_indicators, list) and continuation_indicators:
            medium_score += 1
            reasons.append("Vision supplied continuation indicators.")

        should_merge = strong_score >= 1 or medium_score >= 3

        if not should_merge:
            reasons.append(
                "Insufficient continuity evidence: require one strong "
                "signal or at least three medium signals."
            )

        confidence = min(
            0.99,
            0.50 + (0.22 * strong_score) + (0.07 * medium_score),
        ) if should_merge else min(0.49, 0.10 + (0.08 * medium_score))

        return ContinuationMergeDecision(
            should_merge=should_merge,
            confidence=round(confidence, 4),
            reasons=reasons,
        )

    def _anchor_compatible(self, anchor_type: str, continuation_type: str) -> bool:
        allowed = self.ANCHOR_FOR_CONTINUATION.get(continuation_type, set())

        if allowed:
            return anchor_type in allowed

        # Generic continuation is only accepted for the same family.
        return (
            anchor_type not in self.CONTINUATION_TYPES
            and document_family(anchor_type) == document_family(continuation_type)
        )

    def _is_consecutive_printed_sequence(
        self,
        previous_page: PageInventoryItem,
        current_page: PageInventoryItem,
    ) -> bool:
        previous_number = self._int_feature(previous_page, "printedPageNumber")
        current_number = self._int_feature(current_page, "printedPageNumber")
        previous_total = self._int_feature(previous_page, "printedTotalPages")
        current_total = self._int_feature(current_page, "printedTotalPages")

        return bool(
            previous_number is not None
            and current_number is not None
            and previous_total is not None
            and current_total is not None
            and previous_total == current_total
            and current_number == previous_number + 1
        )

    @classmethod
    def _same_nonempty_identifier(
        cls,
        left: PageInventoryItem,
        right: PageInventoryItem,
        key: str,
    ) -> bool:
        left_value = cls._normalize_identifier(cls._feature(left, key))
        right_value = cls._normalize_identifier(cls._feature(right, key))
        return bool(left_value and right_value and left_value == right_value)

    @classmethod
    def _same_nonempty_text(
        cls,
        left: PageInventoryItem,
        right: PageInventoryItem,
        key: str,
    ) -> bool:
        left_value = cls._normalize_text(cls._feature(left, key))
        right_value = cls._normalize_text(cls._feature(right, key))
        return bool(left_value and right_value and left_value == right_value)

    @classmethod
    def _feature(
            cls,
            page: PageInventoryItem,
            key: str,
    ) -> Any:
        snake_key = cls._camel_to_snake(key)
        candidates = [key, snake_key]

        # 1. Direct PageInventoryItem fields
        for candidate in candidates:
            value = getattr(page, candidate, None)

            if value not in (None, ""):
                return value

        # 2. Structured identifiers
        identifiers = getattr(page, "identifiers", None)

        identifier_aliases = {
            "patientName": "patient_name",
            "claimNumber": "claim_number",
            "authorizationNumber": "authorization_number",
            "billNumber": "bill_number",
            "policyNumber": "policy_number",
            "memberId": "member_id",
            "mrn": "mrn",
            "ipNumber": "ip_number",
        }

        identifier_field = identifier_aliases.get(key)

        if identifiers is not None and identifier_field:
            value = getattr(
                identifiers,
                identifier_field,
                None,
            )

            if value not in (None, ""):
                return value

        # 3. Evidence custom features
        evidence = getattr(page, "evidence", None)
        custom = getattr(
            evidence,
            "custom_features",
            None,
        )

        if isinstance(custom, dict):
            for candidate in candidates:
                value = custom.get(candidate)

                if value not in (None, ""):
                    return value

            # Fingerprint created by DocumentIdentityResolver
            fingerprint = custom.get(
                "documentFingerprint"
            )

            if isinstance(fingerprint, dict):
                fingerprint_aliases = {
                    "patientName": "patient_name",
                    "claimNumber": "claim_number",
                    "authorizationNumber":
                        "authorization_number",
                    "billNumber": "bill_number",
                    "policyNumber": "policy_number",
                    "memberId": "member_id",
                    "printedPageNumber":
                        "printed_page_number",
                    "printedTotalPages":
                        "printed_total_pages",
                    "headerSignature":
                        "header_signature",
                    "templateHint":
                        "template_signature",
                }

                fingerprint_key = (
                    fingerprint_aliases.get(
                        key,
                        snake_key,
                    )
                )

                value = fingerprint.get(
                    fingerprint_key
                )

                if value not in (None, ""):
                    return value

            # Nested Vision payload, when present
            vision = (
                    custom.get("vision")
                    or custom.get("visionEvidence")
                    or custom.get("vision_evidence")
            )

            if isinstance(vision, dict):
                for candidate in candidates:
                    value = vision.get(candidate)

                    if value not in (None, ""):
                        return value

        return None

    @classmethod
    def _bool_feature(cls, page: PageInventoryItem, key: str) -> bool:
        value = cls._feature(page, key)
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in {"true", "1", "yes", "y"}

    @classmethod
    def _int_feature(cls, page: PageInventoryItem, key: str) -> int | None:
        value = cls._feature(page, key)
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_identifier(value: Any) -> str:
        return "".join(
            character
            for character in str(value or "").upper()
            if character.isalnum()
        )

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return " ".join(str(value or "").upper().split())

    @staticmethod
    def _camel_to_snake(value: str) -> str:
        output: list[str] = []
        for character in value:
            if character.isupper():
                output.extend(["_", character.lower()])
            else:
                output.append(character)
        return "".join(output)


__all__ = [
    "ContinuationMergeDecision",
    "SafeContinuationMerge",
]
