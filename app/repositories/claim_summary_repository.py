from datetime import datetime

from sqlalchemy.orm import Session

from app.models.claim_summary import ClaimSummary
from app.models.claim_status_history import ClaimStatusHistory


class ClaimSummaryRepository:

    def __init__(self, db: Session):
        self.db = db

    def find_by_claim_number(
        self,
        portal_connection_id: int,
        portal_claim_number: str,
    ) -> ClaimSummary | None:

        return (
            self.db.query(ClaimSummary)
            .filter(
                ClaimSummary.portal_connection_id == portal_connection_id,
                ClaimSummary.portal_claim_number == portal_claim_number,
            )
            .first()
        )

    def synchronize_claim(
        self,
        portal_connection_id: int,
        hospital_name: str,
        claim: dict,
    ) -> ClaimSummary:

        existing_claim = self.find_by_claim_number(
            portal_connection_id=portal_connection_id,
            portal_claim_number=claim["portal_claim_number"],
        )

        now = datetime.utcnow()

        if existing_claim is None:
            new_claim = ClaimSummary(
                portal_connection_id=portal_connection_id,
                hospital_name=hospital_name,
                payer=claim.get("payer"),
                portal_claim_number=claim.get("portal_claim_number"),
                patient_name=claim.get("patient_name"),
                claimed_amount=claim.get("claimed_amount"),
                approved_amount=claim.get("approved_amount"),
                status=claim.get("status"),
                date_of_admission=claim.get("date_of_admission"),
                date_of_discharge=claim.get("date_of_discharge"),
                current_change_hash=claim.get("current_change_hash"),
                last_synced_at=now,
            )

            self.db.add(new_claim)
            self.db.flush()

            self._insert_history(new_claim, claim, now)

            return new_claim

        existing_claim.last_synced_at = now

        if existing_claim.current_change_hash != claim.get("current_change_hash"):
            existing_claim.payer = claim.get("payer")
            existing_claim.patient_name = claim.get("patient_name")
            existing_claim.claimed_amount = claim.get("claimed_amount")
            existing_claim.approved_amount = claim.get("approved_amount")
            existing_claim.status = claim.get("status")
            existing_claim.date_of_admission = claim.get("date_of_admission")
            existing_claim.date_of_discharge = claim.get("date_of_discharge")
            existing_claim.current_change_hash = claim.get("current_change_hash")

            self._insert_history(existing_claim, claim, now)

        return existing_claim

    def synchronize_claims(
        self,
        portal_connection_id: int,
        hospital_name: str,
        claims: list[dict],
    ) -> list[ClaimSummary]:

        synced_claims = []

        for claim in claims:
            synced_claim = self.synchronize_claim(
                portal_connection_id=portal_connection_id,
                hospital_name=hospital_name,
                claim=claim,
            )
            synced_claims.append(synced_claim)

        self.db.commit()

        return synced_claims

    def _insert_history(
        self,
        claim_summary: ClaimSummary,
        claim: dict,
        observed_at: datetime,
    ) -> None:

        history = ClaimStatusHistory(
            claim_summary_id=claim_summary.id,
            portal_connection_id=claim_summary.portal_connection_id,
            portal_claim_number=claim_summary.portal_claim_number,
            payer=claim.get("payer"),
            status=claim.get("status"),
            claimed_amount=claim.get("claimed_amount"),
            approved_amount=claim.get("approved_amount"),
            date_of_admission=claim.get("date_of_admission"),
            date_of_discharge=claim.get("date_of_discharge"),
            change_hash=claim.get("current_change_hash"),
            observed_at=observed_at,
        )

        self.db.add(history)