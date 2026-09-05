from app.connectors.ihx.ihx_connector import IHXConnector
from app.services.claim_summary_service import ClaimSummaryService

USERNAME = "testpoc@solventek.com"
PASSWORD = "PocHCGDR@2026"


def main():
    with IHXConnector(
            username=USERNAME,
            password=PASSWORD,
            headless=False,
            slow_mo=300,
    ) as connector:
        connector.login_with_graph_otp()
        connector.open_claim_tracking()

        claims = connector.extract_current_page_claims()

        normalized = ClaimSummaryService.normalize_claims(claims)

        for claim in normalized:
            print(claim)
        input("Press Enter to close browser...")


if __name__ == "__main__":
    main()