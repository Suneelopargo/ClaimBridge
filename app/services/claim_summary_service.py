from datetime import datetime
from decimal import Decimal
from typing import Any
import hashlib


class ClaimSummaryService:

    @staticmethod
    def parse_amount(value: str | None) -> Decimal | None:
        if not value:
            return None

        cleaned = (
            value.replace("₹", "")
                 .replace(",", "")
                 .strip()
        )

        if not cleaned:
            return None

        return Decimal(cleaned)

    @staticmethod
    def parse_date(value: str | None):
        if not value:
            return None

        return datetime.strptime(
            value,
            "%d %b %Y"
        ).date()

    @classmethod
    def normalize_claim(
            cls,
            claim: dict[str, Any],
    ) -> dict[str, Any]:

        normalized = {

            "payer":
                claim.get("payer"),

            "portal_claim_number":
                claim.get("portal_claim_number"),

            "patient_name":
                claim.get("patient_name"),

            "claimed_amount":
                cls.parse_amount(
                    claim.get("claimed_amount")
                ),

            "approved_amount":
                cls.parse_amount(
                    claim.get("approved_amount")
                ),

            "status":
                claim.get("status"),

            "date_of_admission":
                cls.parse_date(
                    claim.get("date_of_admission")
                ),

            "date_of_discharge":
                cls.parse_date(
                    claim.get("date_of_discharge")
                ),
        }

        normalized["current_change_hash"] = cls.compute_change_hash(normalized)

        return normalized

    @classmethod
    def normalize_claims(
        cls,
        claims: list[dict],
    ) -> list[dict]:

        return [
            cls.normalize_claim(claim)
            for claim in claims
        ]

    @staticmethod
    def compute_change_hash(claim: dict) -> str:
        hash_input = "|".join([
            str(claim.get("status") or ""),
            str(claim.get("claimed_amount") or ""),
            str(claim.get("approved_amount") or ""),
            str(claim.get("date_of_admission") or ""),
            str(claim.get("date_of_discharge") or ""),
        ])

        return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()