from pathlib import Path
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session
from app.models.claim_summary import ClaimSummary


class ClaimExcelReport:

    @staticmethod
    def generate_claim_summary_excel(db: Session) -> str:
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = reports_dir / f"claim_summary_{timestamp}.xlsx"

        claims = db.query(ClaimSummary).order_by(
            ClaimSummary.last_synced_at.desc()
        ).all()

        data = []

        for claim in claims:
            data.append({
                "Hospital": claim.hospital_name,
                "Payer": claim.payer,
                "Claim No": claim.portal_claim_number,
                "Patient Name": claim.patient_name,
                "Claimed Amount": claim.claimed_amount,
                "Approved Amount": claim.approved_amount,
                "Status": claim.status,
                "DOA": claim.date_of_admission,
                "DOD": claim.date_of_discharge,
                "Last Synced At": claim.last_synced_at,
            })

        df = pd.DataFrame(data)
        df.to_excel(file_path, index=False)

        return str(file_path)