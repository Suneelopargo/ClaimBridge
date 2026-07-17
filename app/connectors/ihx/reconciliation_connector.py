from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from playwright.sync_api import Locator, TimeoutError as PlaywrightTimeoutError

from app.config import (
    IHX_RECONCILIATION_DOWNLOAD_DIR,
    IHX_RECONCILIATION_EXPORT_TIMEOUT_MS,
    IHX_RECONCILIATION_MAX_RETRIES,
    IHX_RECONCILIATION_REPORT_STABILIZE_MS,
    IHX_RECONCILIATION_REPORT_URL,
)
from app.connectors.base_connector import ConnectorError
from app.connectors.ihx import selectors
from app.connectors.ihx.ihx_connector import IHXConnector


logger = logging.getLogger(__name__)


class IHXReconciliationConnector(IHXConnector):
    """Resilient Power BI reconciliation exporter."""

    def open_reconciliation_report(self) -> None:
        self._ensure_page()

        if IHX_RECONCILIATION_REPORT_URL:
            self.goto(IHX_RECONCILIATION_REPORT_URL)
        else:
            self._open_report_from_navigation()

        self.page.wait_for_load_state("domcontentloaded")
        self._click_update_if_visible()

        frame = self._wait_for_power_bi_frame()
        self._wait_for_visual(frame)
        self._stabilize(frame)

    def open_and_download_reconciliation_report(self) -> Path:
        self.open_reconciliation_report()
        return self.download_reconciliation_report()

    def download_reconciliation_report(self) -> Path:
        self._ensure_page()
        last_error: Optional[Exception] = None

        for attempt in range(1, IHX_RECONCILIATION_MAX_RETRIES + 1):
            logger.info(
                "[IHX][Reconciliation] Full export attempt %s/%s",
                attempt,
                IHX_RECONCILIATION_MAX_RETRIES,
            )

            try:
                frame = self._wait_for_power_bi_frame()
                self._wait_for_visual(frame)
                self._stabilize(frame)

                if not self._dialog_visible(frame):
                    self._open_export_dialog(frame)

                self._select_current_layout(frame)
                result = self._download_from_dialog(frame)
                self._capture_stage("05_download_complete")
                return result

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "[IHX][Reconciliation] Attempt %s failed: %s",
                    attempt,
                    exc,
                )
                self._capture_diagnostics(f"attempt_{attempt}_failed")

                if attempt < IHX_RECONCILIATION_MAX_RETRIES:
                    self._recover(attempt)

        raise ConnectorError(
            "IHX reconciliation export failed after "
            f"{IHX_RECONCILIATION_MAX_RETRIES} attempts: {last_error}"
        ) from last_error

    def _open_report_from_navigation(self) -> None:
        self._safe_click(
            self.page.get_by_text(
                selectors.REPORTING_AND_ANALYTICS_TEXT,
                exact=True,
            ).first,
            "Reporting and Analytics",
            timeout_ms=120000,
        )

        try:
            self._safe_click(
                self.page.get_by_text(
                    selectors.RECONCILIATION_TEXT,
                    exact=True,
                ).first,
                "Reconciliation",
                timeout_ms=15000,
                retries=2,
            )
        except Exception:
            logger.info(
                "[IHX][Reconciliation] Separate Reconciliation menu "
                "not found; continuing"
            )

    def _click_update_if_visible(self) -> None:
        locator = self.page.get_by_text(
            selectors.UPDATE_RECONCILIATION_REPORT_TEXT,
            exact=True,
        ).first

        try:
            locator.wait_for(state="visible", timeout=7000)
            self._safe_click(
                locator,
                "Update Reconciliation Report",
                timeout_ms=120000,
                retries=2,
            )
            self.page.wait_for_timeout(2000)
        except Exception:
            logger.info(
                "[IHX][Reconciliation] Update link not visible or not needed"
            )

    def _wait_for_power_bi_frame(self) -> Any:
        elapsed = 0

        while elapsed < IHX_RECONCILIATION_EXPORT_TIMEOUT_MS:
            for frame in self.page.frames:
                if frame == self.page.main_frame:
                    continue

                url = (frame.url or "").lower()
                if (
                    "powerbi" in url
                    or "app.powerbi.com" in url
                    or "wabi-" in url
                ):
                    return frame

                try:
                    if frame.get_by_text(
                        selectors.RECONCILIATION_REPORT_READY_TEXT,
                        exact=False,
                    ).count() > 0:
                        return frame
                except Exception:
                    pass

            self.page.wait_for_timeout(1000)
            elapsed += 1000

        raise ConnectorError("Power BI frame was not detected")

    def _wait_for_visual(self, frame: Any) -> None:
        try:
            frame.get_by_text(
                selectors.RECONCILIATION_REPORT_READY_TEXT,
                exact=False,
            ).first.wait_for(
                state="visible",
                timeout=IHX_RECONCILIATION_EXPORT_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError as exc:
            raise ConnectorError(
                "Power BI reconciliation visual did not finish loading"
            ) from exc

    def _stabilize(self, frame: Any) -> None:
        try:
            frame.locator("body").hover(timeout=5000)
        except Exception:
            pass

        frame.wait_for_timeout(
            IHX_RECONCILIATION_REPORT_STABILIZE_MS
        )
        self._capture_stage("02_report_loaded")

    def _open_export_dialog(self, frame: Any) -> None:
        if self._dialog_visible(frame):
            return

        self._capture_stage("03_before_export")

        strategies = (
            self._direct_export_strategy,
            self._visual_menu_strategy,
            self._global_menu_strategy,
        )
        errors = []

        for strategy in strategies:
            try:
                logger.info(
                    "[IHX][Reconciliation] Trying %s",
                    strategy.__name__,
                )
                strategy(frame)

                if self._dialog_visible(frame):
                    self._capture_stage("04_export_dialog")
                    return
            except Exception as exc:
                errors.append(f"{strategy.__name__}: {exc}")
                self._dismiss_menu(frame)

        raise ConnectorError(
            "Could not open Power BI export dialog. "
            + " | ".join(errors)
        )

    def _direct_export_strategy(self, frame: Any) -> None:
        locator = frame.get_by_text(
            selectors.POWER_BI_EXPORT_DATA_MENU_TEXT,
            exact=True,
        ).first

        if not locator.is_visible(timeout=2000):
            raise ConnectorError("Direct Export data control not visible")

        self._safe_click(locator, "Export data", retries=2)
        self._wait_for_dialog(frame)

    def _visual_menu_strategy(self, frame: Any) -> None:
        containers = frame.locator(selectors.POWER_BI_VISUAL_CONTAINER)

        for index in range(containers.count()):
            visual = containers.nth(index)

            try:
                if not visual.is_visible():
                    continue

                visual.scroll_into_view_if_needed()
                visual.hover()
                frame.wait_for_timeout(700)

                if self._try_more_options(
                    frame,
                    visual,
                    f"visual-{index}",
                ):
                    return
            except Exception:
                continue

        raise ConnectorError(
            "No visual exposed an export-enabled More options menu"
        )

    def _global_menu_strategy(self, frame: Any) -> None:
        try:
            frame.locator("body").hover()
            frame.wait_for_timeout(700)
        except Exception:
            pass

        if not self._try_more_options(frame, frame, "whole-frame"):
            raise ConnectorError(
                "No export-enabled global More options menu found"
            )

    def _try_more_options(
        self,
        frame: Any,
        root: Any,
        description: str,
    ) -> bool:
        candidates = root.locator(selectors.POWER_BI_MORE_OPTIONS)

        for index in range(candidates.count()):
            button = candidates.nth(index)

            try:
                if not button.is_visible():
                    continue

                self._safe_click(
                    button,
                    f"More options {description}-{index}",
                    retries=2,
                    timeout_ms=5000,
                )
                frame.wait_for_timeout(700)

                export_item = frame.get_by_text(
                    selectors.POWER_BI_EXPORT_DATA_MENU_TEXT,
                    exact=True,
                ).first

                if not export_item.is_visible(timeout=2500):
                    self._dismiss_menu(frame)
                    continue

                self._safe_click(
                    export_item,
                    "Export data menu item",
                    retries=2,
                    timeout_ms=5000,
                )
                self._wait_for_dialog(frame)
                return True

            except Exception:
                self._dismiss_menu(frame)

        return False

    def _wait_for_dialog(self, frame: Any) -> None:
        try:
            frame.get_by_text(
                selectors.EXPORT_DIALOG_TITLE_TEXT,
                exact=False,
            ).first.wait_for(state="visible", timeout=20000)
        except PlaywrightTimeoutError as exc:
            raise ConnectorError(
                "Power BI export dialog did not appear"
            ) from exc

    def _dialog_visible(self, frame: Any) -> bool:
        try:
            return frame.get_by_text(
                selectors.EXPORT_DIALOG_TITLE_TEXT,
                exact=False,
            ).first.is_visible(timeout=1200)
        except Exception:
            return False

    def _dismiss_menu(self, frame: Any) -> None:
        try:
            self.page.keyboard.press("Escape")
            frame.wait_for_timeout(300)
        except Exception:
            pass

    def _select_current_layout(self, frame: Any) -> None:
        option = frame.get_by_text(
            selectors.DATA_WITH_CURRENT_LAYOUT_TEXT,
            exact=True,
        ).first
        self._safe_click(
            option,
            "Data with current layout",
            retries=2,
            timeout_ms=15000,
        )

    def _download_from_dialog(self, frame: Any) -> Path:
        download_dir = Path(IHX_RECONCILIATION_DOWNLOAD_DIR)
        download_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = (
            download_dir / f"ihx_reconciliation_{timestamp}.xlsx"
        )

        for attempt in range(1, 4):
            try:
                export_button = self._find_export_button(frame)

                with self.page.expect_download(
                        timeout=IHX_RECONCILIATION_EXPORT_TIMEOUT_MS
                ) as download_info:
                    export_button.scroll_into_view_if_needed()

                    frame.wait_for_timeout(500)

                    export_button.click(force=True)

                download = download_info.value

                failure = download.failure()
                if failure:
                    raise ConnectorError(failure)

                suffix = Path(
                    download.suggested_filename
                ).suffix.lower()

                if suffix in {".xlsx", ".xls"}:
                    target = target.with_suffix(suffix)

                download.save_as(str(target))
                self._validate_download(target)

                logger.info(
                    "[IHX][Reconciliation] Downloaded %s (%s bytes)",
                    target,
                    target.stat().st_size,
                )
                return target

            except Exception as exc:
                logger.warning(
                    "[IHX][Reconciliation] Download trigger %s/3 "
                    "failed: %s",
                    attempt,
                    exc,
                )

                if attempt >= 3:
                    raise ConnectorError(
                        "Export dialog opened but download failed"
                    ) from exc

                frame.wait_for_timeout(1000)

                if not self._dialog_visible(frame):
                    self._open_export_dialog(frame)
                    self._select_current_layout(frame)

        raise ConnectorError("Unexpected download retry failure")

    def _find_export_button(self, frame):
        candidates = (
            frame.locator("[data-testid='export-btn']").first,
            frame.get_by_role(
                "button",
                name=selectors.EXPORT_BUTTON_TEXT,
                exact=True,
            ).first,
            frame.locator("button:has-text('Export')").first,
            frame.get_by_text(
                selectors.EXPORT_BUTTON_TEXT,
                exact=True,
            ).last,
        )

        for locator in candidates:
            try:
                locator.wait_for(state="visible", timeout=5000)

                if locator.is_enabled():
                    return locator

            except Exception:
                pass

        raise ConnectorError("Export button not found")

    @staticmethod
    def _validate_download(path: Path) -> None:
        if not path.exists():
            raise ConnectorError(
                "Downloaded reconciliation file was not saved"
            )

        if path.stat().st_size <= 0:
            raise ConnectorError(
                "Downloaded reconciliation file is empty"
            )

        if path.suffix.lower() not in {".xlsx", ".xls"}:
            raise ConnectorError(
                f"Unexpected reconciliation export extension: {path.suffix}"
            )

    def _recover(self, attempt: int) -> None:
        self._dismiss_menu(self.page)

        if attempt == 1:
            self.page.wait_for_timeout(2000)
            return

        logger.info(
            "[IHX][Reconciliation] Refreshing report before retry"
        )

        self.page.reload(
            wait_until="domcontentloaded",
            timeout=IHX_RECONCILIATION_EXPORT_TIMEOUT_MS,
        )
        self.page.wait_for_timeout(2500)

        self._click_update_if_visible()
        frame = self._wait_for_power_bi_frame()
        self._wait_for_visual(frame)
        self._stabilize(frame)

    def _safe_click(
        self,
        locator: Locator,
        description: str,
        retries: int = 3,
        timeout_ms: int = 10000,
    ) -> None:
        last_error: Optional[Exception] = None

        for attempt in range(1, retries + 1):
            try:
                locator.wait_for(
                    state="visible",
                    timeout=timeout_ms,
                )
                locator.scroll_into_view_if_needed()

                try:
                    locator.hover(timeout=3000)
                except Exception:
                    pass

                locator.click(timeout=timeout_ms)

                logger.info(
                    "[IHX][Reconciliation] Clicked %s (%s/%s)",
                    description,
                    attempt,
                    retries,
                )
                return
            except Exception as exc:
                last_error = exc
                self.page.wait_for_timeout(700)

        raise ConnectorError(
            f"Could not click {description}"
        ) from last_error

    def _capture_stage(self, name: str) -> None:
        self.safe_screenshot(name)

    def _capture_diagnostics(self, name: str) -> None:
        self.safe_screenshot(name)

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self.screenshot_dir / f"{name}_{timestamp}.html"
            path.write_text(self.page.content(), encoding="utf-8")
            logger.info(
                "[IHX][Reconciliation] Saved HTML diagnostic: %s",
                path,
            )
        except Exception as exc:
            logger.warning(
                "[IHX][Reconciliation] HTML diagnostic failed: %s",
                exc,
            )
