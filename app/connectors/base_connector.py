# app/connectors/base_connector.py

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)


logger = logging.getLogger(__name__)


class ConnectorError(Exception):
    """Base exception for connector failures."""


class BrowserNotStartedError(ConnectorError):
    """Raised when browser/page is used before startup."""


class BaseConnector:
    def __init__(
        self,
        connector_name: str,
        headless: bool = True,
        timeout: int = 30000,
        slow_mo: int = 0,
    ):
        self.connector_name = connector_name
        self.headless = headless
        self.timeout = timeout
        self.slow_mo = slow_mo

        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        self.screenshot_dir = Path("screenshots") / connector_name
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def start_browser(self) -> Page:
        logger.info("[%s] Starting browser", self.connector_name)

        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
        )

        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.page.set_default_timeout(self.timeout)

        return self.page

    def close_browser(self) -> None:
        logger.info("[%s] Closing browser", self.connector_name)

        try:
            if self.context:
                self.context.close()

            if self.browser:
                self.browser.close()

            if self.playwright:
                self.playwright.stop()

        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None

    def goto(self, url: str) -> Page:
        self._ensure_page()
        logger.info("[%s] Opening URL: %s", self.connector_name, url)

        self.page.goto(url, wait_until="domcontentloaded")
        return self.page

    def wait_for_element(self, selector: str, timeout: Optional[int] = None):
        self._ensure_page()
        return self.page.wait_for_selector(
            selector,
            timeout=timeout or self.timeout,
        )

    def click(self, selector: str, timeout: Optional[int] = None) -> None:
        self._ensure_page()
        logger.info("[%s] Clicking selector: %s", self.connector_name, selector)

        self.wait_for_element(selector, timeout)
        self.page.locator(selector).click()

    def fill(
        self,
        selector: str,
        value: str,
        timeout: Optional[int] = None,
    ) -> None:
        self._ensure_page()
        logger.info("[%s] Filling selector: %s", self.connector_name, selector)

        self.wait_for_element(selector, timeout)
        self.page.locator(selector).fill(value)

    def text(self, selector: str, timeout: Optional[int] = None) -> str:
        self._ensure_page()
        self.wait_for_element(selector, timeout)

        return self.page.locator(selector).inner_text().strip()

    def wait_for_load(self) -> None:
        self._ensure_page()
        self.page.wait_for_load_state("networkidle")

    def screenshot(self, name: str = "screenshot") -> str:
        self._ensure_page()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = self.screenshot_dir / f"{name}_{timestamp}.png"

        self.page.screenshot(path=str(file_path), full_page=True)

        logger.info(
            "[%s] Screenshot captured: %s",
            self.connector_name,
            file_path,
        )

        return str(file_path)

    def safe_screenshot(self, name: str = "error") -> Optional[str]:
        try:
            return self.screenshot(name)
        except Exception as exc:
            logger.warning(
                "[%s] Screenshot failed: %s",
                self.connector_name,
                exc,
            )
            return None

    def _ensure_page(self) -> None:
        if self.page is None:
            raise BrowserNotStartedError(
                f"{self.connector_name}: browser/page is not started. "
                "Call start_browser() first."
            )

    def __enter__(self):
        self.start_browser()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_value:
            logger.exception(
                "[%s] Connector failed",
                self.connector_name,
            )
            self.safe_screenshot("connector_error")

        self.close_browser()