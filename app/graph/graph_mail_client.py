import os
import re
import time
from typing import Optional
from datetime import datetime, timezone
import msal
import requests
from dotenv import load_dotenv

load_dotenv()


class GraphMailClient:
    def __init__(
        self,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        mailbox: Optional[str] = None,
    ):
        self.tenant_id = tenant_id or os.getenv("GRAPH_TENANT_ID")
        self.client_id = client_id or os.getenv("GRAPH_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("GRAPH_CLIENT_SECRET")
        self.mailbox = mailbox or os.getenv("GRAPH_MAILBOX")

        if not all([
            self.tenant_id,
            self.client_id,
            self.client_secret,
            self.mailbox,
        ]):
            raise RuntimeError("Graph mail configuration is missing")

    def get_access_token(self) -> str:
        app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=self.client_secret,
        )

        result = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )

        if "access_token" not in result:
            raise RuntimeError(f"Unable to get Graph token: {result}")

        return result["access_token"]

    def read_latest_messages(self, top: int = 10) -> list[dict]:
        token = self.get_access_token()

        url = (
            f"https://graph.microsoft.com/v1.0/users/{self.mailbox}/messages"
            f"?$top={top}"
            "&$orderby=receivedDateTime desc"
            "&$select=subject,from,receivedDateTime,bodyPreview"
        )

        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Graph mail read failed: {response.status_code} {response.text}"
            )

        return response.json().get("value", [])

    def extract_otp_from_text(self, text: str) -> Optional[str]:
        if not text:
            return None

        match = re.search(r"\b\d{5}\b", text)
        if match:
            return match.group(0)

        return None

    def read_latest_otp(
            self,
            poll_seconds: int = 120,
            interval_seconds: int = 5,
            received_after: datetime | None = None,
    ) -> str:
        deadline = time.time() + poll_seconds

        while time.time() < deadline:
            messages = self.read_latest_messages(top=10)

            for message in messages:
                if received_after:
                    received_at_text = message.get("receivedDateTime")
                    if received_at_text:
                        received_at = datetime.fromisoformat(
                            received_at_text.replace("Z", "+00:00")
                        )

                        if received_at < received_after:
                            continue

                searchable_text = " ".join([
                    message.get("subject") or "",
                    message.get("bodyPreview") or "",
                ])

                otp = self.extract_otp_from_text(searchable_text)
                if otp:
                    return otp

            time.sleep(interval_seconds)

        raise TimeoutError("OTP email not received within polling window")