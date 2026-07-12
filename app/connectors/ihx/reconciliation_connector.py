# app/connectors/ihx/reconciliation_connector.py

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.sync_api import Frame, Locator, TimeoutError as PlaywrightTimeoutError

from app.config import (
    IHX_RECONCILIATION_DOWNLOAD_DIR,
    IHX_RECONCILIATION_EXPORT_TIMEOUT_MS,
    IHX_RECONCILIATION_REPORT_URL,
)
from app.connectors.base_connector import ConnectorError
from app.connectors.ihx import selectors
from app.connectors.ihx.ihx_connector import IHXConnector


logger = logging.getLogger(__name__)


class IHXReconciliationConnector(IHXConnector):
    """
    Downloads the IHX reconciliation workbook through the embedded Power BI
    report.

    Login and OTP are inherited from IHXConnector. This connector intentionally
    downloads the workbook instead of scraping the reconciliation grid.
    """

    def open_reconciliation_report(self) -> None:
        self._ensure_page()

        if IHX_RECONCILIATION_REPORT_URL:
            logger.info(
                "[IHX][Reconciliation] Opening configured report URL"
            )
            self.goto(IHX_RECONCILIATION_REPORT_URL)
        else:
            logger.info(
                "[IHX][Reconciliation] Using IHX navigation"
            )
            self._open_report_from_navigation()

        self.page.wait_for_load_state("domcontentloaded")

        self._click_update_reconciliation_report_if_available()

        report_frame = self._wait_for_power_bi_frame()

        self._wait_for_reconciliation_visual(report_frame)

        logger.info(
            "[IHX][Reconciliation] Reconciliation report fully loaded"
        )

    def download_reconciliation_report(self) -> Path:
        """
        Opens Power BI export, selects 'Data with current layout', downloads the
        workbook, and saves it in the configured reconciliation download folder.
        """
        self._ensure_page()

        report_frame = self._wait_for_power_bi_frame()
        self._open_export_dialog(report_frame)
        self._select_current_layout(report_frame)

        download_dir = Path(IHX_RECONCILIATION_DOWNLOAD_DIR)
        download_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_path = download_dir / f"ihx_reconciliation_{timestamp}.xlsx"

        export_button = self._find_visible_text_button(
            report_frame,
            selectors.EXPORT_BUTTON_TEXT,
        )

        try:
            with self.page.expect_download(
                timeout=IHX_RECONCILIATION_EXPORT_TIMEOUT_MS
            ) as download_info:
                export_button.click()

            download = download_info.value

            suggested_suffix = Path(download.suggested_filename).suffix.lower()
            if suggested_suffix in {".xlsx", ".xls"}:
                target_path = target_path.with_suffix(suggested_suffix)

            download.save_as(str(target_path))

        except Exception as exc:
            self.safe_screenshot("reconciliation_export_failed")
            logger.exception("[IHX][Reconciliation] Export download failed")
            raise ConnectorError(
                "IHX reconciliation report download failed"
            ) from exc

        if not target_path.exists() or target_path.stat().st_size == 0:
            raise ConnectorError(
                "IHX reconciliation export completed but no valid file was saved"
            )

        logger.info(
            "[IHX][Reconciliation] Report downloaded: %s (%s bytes)",
            target_path,
            target_path.stat().st_size,
        )
        return target_path

    def open_and_download_reconciliation_report(self) -> Path:
        self.open_reconciliation_report()
        return self.download_reconciliation_report()

    def _open_report_from_navigation(self) -> None:
        """
        Navigates through the IHX side menu. The UI observed in the supplied
        screenshots shows 'Reporting and Analytics' and 'Reconciliation'.
        """
        reporting_link = self.page.get_by_text(
            selectors.REPORTING_AND_ANALYTICS_TEXT,
            exact=True,
        ).first

        try:
            reporting_link.wait_for(state="visible", timeout=30000)
            reporting_link.click()
        except Exception as exc:
            self.safe_screenshot("reporting_menu_not_found")
            raise ConnectorError(
                "Could not find IHX 'Reporting and Analytics' navigation item. "
                "Set IHX_RECONCILIATION_REPORT_URL in .env if a direct URL is available."
            ) from exc

        # Some IHX versions open the reconciliation visual directly; others show
        # a separate Reconciliation menu item.
        reconciliation_link = self.page.get_by_text(
            selectors.RECONCILIATION_TEXT,
            exact=True,
        ).first

        try:
            reconciliation_link.wait_for(state="visible", timeout=15000)
            reconciliation_link.click()
        except Exception:
            logger.info(
                "[IHX][Reconciliation] Separate Reconciliation menu item not "
                "found; continuing with the opened analytics page"
            )

    def _wait_for_power_bi_frame(self) -> Frame:
        """
        Finds the embedded Power BI frame. It avoids relying only on iframe
        position because the portal can add other frames.
        """
        deadline_ms = IHX_RECONCILIATION_EXPORT_TIMEOUT_MS
        elapsed = 0
        step = 1000

        while elapsed < deadline_ms:
            for frame in self.page.frames:
                if frame == self.page.main_frame:
                    continue

                url = (frame.url or "").lower()
                if "powerbi" in url or "app.powerbi.com" in url:
                    return frame

                try:
                    if frame.get_by_text(
                        selectors.EXPORT_DIALOG_TITLE_TEXT,
                        exact=False,
                    ).count() > 0:
                        return frame
                except Exception:
                    continue

            self.page.wait_for_timeout(step)
            elapsed += step

        self.safe_screenshot("power_bi_frame_not_found")
        raise ConnectorError(
            "Embedded Power BI report frame was not detected"
        )

    def _open_export_dialog(self, frame: Frame) -> None:
        if self._dialog_is_visible(frame):
            return

        logger.info(
            "[IHX][Reconciliation] Looking for Power BI export controls"
        )

        # Power BI often hides visual controls until the mouse is over the visual.
        visual_containers = frame.locator(
            selectors.POWER_BI_VISUAL_CONTAINER
        )

        for index in range(visual_containers.count()):
            visual = visual_containers.nth(index)

            try:
                if not visual.is_visible():
                    continue

                visual.hover()
                frame.wait_for_timeout(1000)

                more_options = visual.locator(
                    selectors.POWER_BI_MORE_OPTIONS
                )

                for button_index in range(more_options.count()):
                    menu_button = more_options.nth(button_index)

                    if not menu_button.is_visible():
                        continue

                    logger.info(
                        "[IHX][Reconciliation] Opening visual More options"
                    )

                    menu_button.click()
                    frame.wait_for_timeout(1000)

                    export_menu_item = frame.get_by_text(
                        selectors.POWER_BI_EXPORT_DATA_MENU_TEXT,
                        exact=True,
                    ).first

                    if export_menu_item.is_visible():
                        export_menu_item.click()
                        self._wait_for_export_dialog(frame)
                        return

            except Exception:
                continue

        # Fallback: search the whole frame after hovering over the report body.
        try:
            frame.locator("body").hover()
            frame.wait_for_timeout(1000)
        except Exception:
            pass

        more_options = frame.locator(
            selectors.POWER_BI_MORE_OPTIONS
        )

        for index in range(more_options.count()):
            candidate = more_options.nth(index)

            try:
                if not candidate.is_visible():
                    continue

                candidate.click()
                frame.wait_for_timeout(1000)

                export_menu_item = frame.get_by_text(
                    selectors.POWER_BI_EXPORT_DATA_MENU_TEXT,
                    exact=True,
                ).first

                if export_menu_item.is_visible():
                    export_menu_item.click()
                    self._wait_for_export_dialog(frame)
                    return

            except Exception:
                continue

        self.safe_screenshot(
            "power_bi_more_options_not_found"
        )

        raise ConnectorError(
            "Power BI report loaded, but no export-enabled visual "
            "More options button was found"
        )

    def _wait_for_export_dialog(self, frame: Frame) -> None:
        try:
            frame.get_by_text(
                selectors.EXPORT_DIALOG_TITLE_TEXT,
                exact=False,
            ).first.wait_for(
                state="visible",
                timeout=IHX_RECONCILIATION_EXPORT_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError as exc:
            self.safe_screenshot("power_bi_export_dialog_not_found")
            raise ConnectorError(
                "Power BI export dialog did not open"
            ) from exc

    def _dialog_is_visible(self, frame: Frame) -> bool:
        try:
            return frame.get_by_text(
                selectors.EXPORT_DIALOG_TITLE_TEXT,
                exact=False,
            ).first.is_visible(timeout=1000)
        except Exception:
            return False

    def _select_current_layout(self, frame: Frame) -> None:
        option = frame.get_by_text(
            selectors.DATA_WITH_CURRENT_LAYOUT_TEXT,
            exact=True,
        ).first

        try:
            option.wait_for(state="visible", timeout=15000)
            option.click()
            logger.info(
                "[IHX][Reconciliation] Selected 'Data with current layout'"
            )
        except Exception as exc:
            self.safe_screenshot("current_layout_option_not_found")
            raise ConnectorError(
                "Could not select Power BI 'Data with current layout'"
            ) from exc

    @staticmethod
    def _find_visible_text_button(frame: Frame, text: str) -> Locator:
        button = frame.get_by_role("button", name=text, exact=True).first

        try:
            button.wait_for(state="visible", timeout=15000)
            return button
        except Exception:
            fallback = frame.get_by_text(text, exact=True).first
            fallback.wait_for(state="visible", timeout=15000)
            return fallback
