from app.connectors.ihx.ihx_connector import IHXConnector
from app.database import SessionLocal
from app.repositories.claim_summary_repository import ClaimSummaryRepository
from app.services.claim_summary_service import ClaimSummaryService


USERNAME = "testpoc@solventek.com"
PASSWORD = "PocHCGDR@2026"

PORTAL_CONNECTION_ID = 1
HOSPITAL_NAME = "HCG Demo Hospital"


def main():
    db = SessionLocal()

    try:
        with IHXConnector(
            username=USERNAME,
            password=PASSWORD,
            headless=False,
            slow_mo=300,
        ) as connector:
            connector.login_with_graph_otp()
            connector.open_claim_tracking()

            raw_claims = connector.extract_all_claim_pages()
            normalized_claims = ClaimSummaryService.normalize_claims(raw_claims)

            repository = ClaimSummaryRepository(db)
            synced_claims = repository.synchronize_claims(
                portal_connection_id=PORTAL_CONNECTION_ID,
                hospital_name=HOSPITAL_NAME,
                claims=normalized_claims,
            )

            print(f"Raw claims extracted: {len(raw_claims)}")
            print(f"Claims synced to DB: {len(synced_claims)}")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()