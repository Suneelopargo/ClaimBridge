# app/connectors/ihx/ihx_connector.py

import logging
from typing import Optional
from datetime import datetime, timezone

from app.config import IHX_RECONCILIATION_EXPORT_TIMEOUT_MS
from app.connectors.base_connector import BaseConnector, ConnectorError
from app.connectors.ihx import selectors
from app.graph.graph_mail_client import GraphMailClient


logger = logging.getLogger(__name__)


class IHXConnector(BaseConnector):
    def __init__(
        self,
        username: str,
        password: str,
        headless: bool = True,
        timeout: int = 120000,
        slow_mo: int = 200,
    ):
        super().__init__(
            connector_name="ihx",
            headless=headless,
            timeout=timeout,
            slow_mo=slow_mo,
        )

        self.username = username
        self.password = password

    def open_login_page(self) -> None:
        self.goto(selectors.LOGIN_URL)
        self.handle_cookie_popup()
        self.wait_for_element(selectors.USERNAME)
        logger.info("[IHX] Login page opened")

    def enter_credentials(self) -> None:
        self.fill(selectors.USERNAME, self.username)
        self.fill(selectors.PASSWORD, self.password)
        logger.info("[IHX] Username/password entered")

    def submit_login(self) -> None:
        self.click(selectors.LOGIN_BUTTON)

        logger.info("=" * 80)
        logger.info("[IHX] Login button clicked")
        logger.info("=" * 80)

        self.page.wait_for_timeout(5000)

        try:
            logger.info("[IHX] URL After Login : %s", self.page.url)
            logger.info("[IHX] Title After Login : %s", self.page.title())
        except Exception as exc:
            logger.warning("Unable to read URL/Title : %s", exc)

    def wait_for_otp_screen(self) -> bool:
        try:
            logger.info("=" * 80)
            logger.info("[IHX] Waiting for OTP screen...")
            logger.info("=" * 80)

            self.page.wait_for_timeout(5000)

            logger.info("[IHX] Current URL : %s", self.page.url)

            try:
                logger.info("[IHX] Current Title : %s", self.page.title())
            except Exception:
                pass

            try:
                html = self.page.content()
                logger.info("=" * 80)
                logger.info("PAGE HTML START")
                logger.info(html[:10000])
                logger.info("PAGE HTML END")
                logger.info("=" * 80)
            except Exception as exc:
                logger.warning("Unable to read HTML : %s", exc)

            self.safe_screenshot("before_otp_wait")

            body_text = self.page.locator("body").inner_text().lower()

            if "captcha" in body_text:
                raise ConnectorError("IHX displayed CAPTCHA")

            if "access denied" in body_text:
                raise ConnectorError("IHX Access Denied")

            if "invalid" in body_text:
                raise ConnectorError("Invalid Username or Password")

            logger.info("[IHX] Waiting for OTP field...")

            self.page.wait_for_selector(
                selectors.OTP_DIGIT_PREFIX.format(0),
                timeout=60000,
                state="visible",
            )

            logger.info("[IHX] OTP screen detected")
            return True

        except Exception as exc:
            logger.exception("[IHX] OTP screen detection failed")
            try:
                logger.info("[IHX] Final URL : %s", self.page.url)
                logger.info("[IHX] Final Title : %s", self.page.title())
            except Exception:
                pass

            self.safe_screenshot("otp_screen_not_found")
            raise ConnectorError("IHX OTP screen not detected") from exc


    def login_until_otp(self) -> dict:
        try:
            self.open_login_page()
            self.enter_credentials()
            self.submit_login()
            otp_screen_found = self.wait_for_otp_screen()

            return {
                "success": True,
                "message": "IHX login submitted successfully. OTP screen detected.",
                "otpScreenFound": otp_screen_found,
            }

        except Exception as exc:
            self.safe_screenshot("ihx_login_failed")
            logger.exception("[IHX] Login failed")
            raise ConnectorError("IHX login failed") from exc

    def fill_otp(self, otp: str) -> None:
        if not otp or len(otp) != 5 or not otp.isdigit():
            raise ConnectorError("IHX OTP must be a 5-digit number")

        for index, digit in enumerate(otp):
            selector = selectors.OTP_DIGIT_PREFIX.format(index)
            self.fill(selector, digit)

        logger.info("[IHX] OTP entered")

    def submit_otp(self) -> None:
        self.click(selectors.VERIFY_OTP_BUTTON)
        logger.info("[IHX] OTP verification submitted")

    def verify_otp(self, otp: str) -> dict:
        try:
            self.fill_otp(otp)
            self.submit_otp()

            self.page.wait_for_load_state("networkidle")

            return {
                "success": True,
                "message": "IHX OTP submitted successfully",
            }

        except Exception as exc:
            self.safe_screenshot("ihx_otp_failed")
            logger.exception("[IHX] OTP verification failed")
            raise ConnectorError("IHX OTP verification failed") from exc

    def handle_cookie_popup(self) -> None:
        cookie_selectors = [
            selectors.COOKIE_ACCEPT_ALL_BUTTON,
            selectors.COOKIE_ACCEPT_BUTTON,
            selectors.COOKIE_CLOSE_BUTTON,
        ]

        for selector in cookie_selectors:
            try:
                button = self.page.locator(selector).first
                if button.is_visible(timeout=3000):
                    button.click()
                    logger.info("[IHX] Cookie popup handled using selector: %s", selector)
                    return
            except Exception:
                continue

        logger.info("[IHX] Cookie popup not found")

    def login_with_graph_otp(self) -> dict:
        otp_requested_at = datetime.now(timezone.utc)

        self.login_until_otp()

        graph_client = GraphMailClient()
        otp = graph_client.read_latest_otp(
            received_after=otp_requested_at,
            poll_seconds=180,
            interval_seconds=5,
        )

        otp_result = self.verify_otp(otp)
        self.page.wait_for_url("**/claims/in-patient", timeout=60000)

        return {
            "success": True,
            "message": "IHX login completed using Graph OTP",
            "otpResult": otp_result,
        }

    def open_claim_tracking(self) -> None:
        self.goto(selectors.INPATIENT_CLAIMS_URL)
        self.wait_for_element(selectors.CLAIMS_TABLE_HEADER, timeout=60000)
        self.wait_for_element(selectors.CLAIMS_TABLE_BODY, timeout=60000)
        logger.info("[IHX] In-patient claims page opened")

    def extract_table_headers(self) -> list[str]:
        self.wait_for_element(selectors.CLAIMS_TABLE_HEADER)

        headers = self.page.locator("table thead th").all_inner_texts()

        return [
            header.replace("\n", " ").strip()
            for header in headers
            if header.strip()
        ]

    def extract_current_page_claims(self) -> list[dict]:
        self.wait_for_element(selectors.CLAIM_ROWS, timeout=60000)

        headers = self.extract_table_headers()
        rows = self.page.locator(selectors.CLAIM_ROWS)

        claims = []

        for row_index in range(rows.count()):
            row = rows.nth(row_index)
            cells = [
                cell.replace("\n", " ").strip()
                for cell in row.locator("td").all_inner_texts()
            ]

            if len(cells) != len(headers):
                logger.warning(
                    "[IHX] Skipping row due to header/cell mismatch. "
                    "headers=%s cells=%s",
                    len(headers),
                    len(cells),
                )
                continue

            row_data = dict(zip(headers, cells))

            claims.append({
                "payer": row_data.get("Payer"),
                "portal_claim_number": row_data.get("Claim No."),
                "patient_name": row_data.get("Patient Name"),
                "claimed_amount": row_data.get("Claimed Amount"),
                "approved_amount": row_data.get("Approved Amount"),
                "status": row_data.get("Status"),
                "date_of_admission": row_data.get("DOA"),
                "date_of_discharge": row_data.get("DOD"),
            })

        logger.info("[IHX] Extracted %s claims from current page", len(claims))
        return claims

    def has_next_page(self) -> bool:
        next_button = self.page.locator(selectors.PAGINATION_NEXT)

        if next_button.count() == 0:
            return False

        class_value = next_button.first.get_attribute("class") or ""

        return "ant-pagination-disabled" not in class_value

    def goto_next_page(self) -> bool:
        if not self.has_next_page():
            logger.info("[IHX] No next page available")
            return False

        first_claim_before = None

        try:
            first_claim_before = (
                self.page.locator(selectors.CLAIM_ROWS)
                .first
                .locator("td")
                .nth(1)
                .inner_text()
                .strip()
            )
        except Exception:
            pass

        self.page.locator(selectors.PAGINATION_NEXT).click()

        if first_claim_before:
            self.page.wait_for_function(
                """
                (oldClaimNo) => {
                    const rows = document.querySelectorAll("table tbody tr");
                    if (!rows || rows.length === 0) return false;

                    const firstRowCells = rows[0].querySelectorAll("td");
                    if (!firstRowCells || firstRowCells.length < 2) return false;

                    return firstRowCells[1].innerText.trim() !== oldClaimNo;
                }
                """,
                arg=first_claim_before,
                timeout=60000,
            )
        else:
            self.page.wait_for_load_state("networkidle")

        logger.info("[IHX] Moved to next claims page")
        return True

    def extract_all_claim_pages(
            self,
            start_page: int = 1,
            max_pages: int | None = None,
    ) -> list[dict]:

        all_claims = []

        self.go_to_page(start_page)

        page_number = start_page
        pages_processed = 0

        while True:
            logger.info("=" * 70)
            logger.info("[IHX] Processing Page %s", page_number)
            logger.info("=" * 70)

            page_claims = self.extract_current_page_claims()

            print(f"Page {page_number}: {len(page_claims)} claims")
            print(
                "First claim:",
                page_claims[0]["portal_claim_number"] if page_claims else None,
            )

            all_claims.extend(page_claims)
            pages_processed += 1

            logger.info(
                "[IHX] Page %s : %s claims extracted",
                page_number,
                len(page_claims),
            )

            if max_pages and pages_processed >= max_pages:
                logger.info("[IHX] Batch page limit reached: %s", max_pages)
                break
            self.page.wait_for_timeout(5000)
            moved = self.goto_next_page_with_retry()
            if not moved:
                break

            page_number += 1

        unique_claims = {
            (claim.get("payer"), claim.get("portal_claim_number")): claim
            for claim in all_claims
            if claim.get("portal_claim_number")
               and claim.get("portal_claim_number") != "-"
        }

        logger.info(
            "[IHX] Extracted %s unique claims from page %s onward. Pages processed: %s",
            len(unique_claims),
            start_page,
            pages_processed,
        )

        return list(unique_claims.values())

    def go_to_page(self, target_page: int) -> None:
        if target_page <= 1:
            return

        current_page = 1

        while current_page < target_page:
            moved = self.goto_next_page_with_retry()
            if not moved:
                raise ConnectorError(f"Unable to reach page {target_page}")

            current_page += 1

        logger.info("[IHX] Reached page %s", target_page)

    def goto_next_page_with_retry(self, retries: int = 3) -> bool:
        last_error = None

        for attempt in range(1, retries + 1):
            try:
                return self.goto_next_page()
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "[IHX] Next page attempt %s/%s failed: %s",
                    attempt,
                    retries,
                    exc,
                )
                self.safe_screenshot(f"next_page_failed_attempt_{attempt}")
                self.page.wait_for_timeout(5000)

        raise ConnectorError("IHX pagination failed after retries") from last_error

    def _click_update_reconciliation_report_if_available(self) -> None:
        update_link = self.page.get_by_text(
            selectors.UPDATE_RECONCILIATION_REPORT_TEXT,
            exact=True,
        ).first

        try:
            update_link.wait_for(state="visible", timeout=10000)

            logger.info(
                "[IHX][Reconciliation] Clicking Update Reconciliation Report"
            )

            update_link.click()

            self.page.wait_for_timeout(3000)

        except Exception:
            logger.info(
                "[IHX][Reconciliation] Update Reconciliation Report "
                "link not found or not required"
            )

    def _wait_for_reconciliation_visual(self, frame) -> None:
        """
        Wait until the embedded Power BI report has rendered actual report data.

        Detecting the iframe alone is insufficient because Power BI may still be
        displaying its loading logo.
        """
        logger.info(
            "[IHX][Reconciliation] Waiting for Power BI visual to load"
        )

        ready_text = frame.get_by_text(
            selectors.RECONCILIATION_REPORT_READY_TEXT,
            exact=False,
        ).first

        try:
            ready_text.wait_for(
                state="visible",
                timeout=IHX_RECONCILIATION_EXPORT_TIMEOUT_MS,
            )

            # Give Power BI a few seconds to finish visual controls and menus.
            frame.wait_for_timeout(5000)

            logger.info(
                "[IHX][Reconciliation] Power BI visual is ready"
            )

        except Exception as exc:
            self.safe_screenshot(
                "reconciliation_power_bi_visual_not_ready"
            )

            raise ConnectorError(
                "Power BI reconciliation report did not finish loading"
            ) from exc

