# app/services/rule_engine/manifest_accessor.py

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ManifestDocument:
    document_type: str
    normalized_document_type: str
    file_name: str | None
    page_numbers: list[int]
    confidence: float | None
    raw: dict[str, Any]


class ManifestAccessor:
    """
    Provides a stable interface over the claim-packet manifest.

    Operators should use this class instead of directly parsing the
    manifest dictionary.
    """

    DOCUMENT_LIST_KEYS = (
        "documents",
        "documentList",
        "classifiedDocuments",
        "items",
    )

    DOCUMENT_TYPE_KEYS = (
        "documentType",
        "document_type",
        "docType",
        "doc_type",
        "type",
        "classification",
        "category",
    )

    FILE_NAME_KEYS = (
        "fileName",
        "filename",
        "file_name",
        "sourceFileName",
        "source_file_name",
    )

    PAGE_NUMBER_KEYS = (
        "pageNumbers",
        "page_numbers",
        "pages",
        "pageNumber",
        "page_number",
    )

    CONFIDENCE_KEYS = (
        "confidence",
        "classificationConfidence",
        "classification_confidence",
    )

    def __init__(self, manifest: dict[str, Any] | None):
        self._manifest = manifest or {}
        self._documents = self._build_documents()

    @property
    def raw(self) -> dict[str, Any]:
        return self._manifest

    @property
    def documents(self) -> list[ManifestDocument]:
        return list(self._documents)

    def document_types(self) -> list[str]:
        return [
            document.document_type
            for document in self._documents
            if document.document_type
        ]

    def normalized_document_types(self) -> set[str]:
        return {
            document.normalized_document_type
            for document in self._documents
            if document.normalized_document_type
        }

    def has_document(self, document_type: str) -> bool:
        return bool(self.find_documents(document_type))

    def find_documents(
        self,
        document_type: str,
    ) -> list[ManifestDocument]:
        required_type = self.normalize_document_type(
            document_type
        )

        if not required_type:
            return []

        return [
            document
            for document in self._documents
            if self._matches_document_type(
                required_type=required_type,
                actual_type=document.normalized_document_type,
            )
        ]

    @classmethod
    def normalize_document_type(
        cls,
        value: Any,
    ) -> str:
        text = str(value or "").strip().lower()

        if not text:
            return ""

        text = text.replace("&", " and ")
        text = re.sub(r"[/_-]+", " ", text)
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        aliases = {
            "claim form part b": "claim form part b",
            "part b claim form": "claim form part b",
            "claim form b": "claim form part b",
            "pre authorization approval": "approval letter",
            "pre authorisation approval": "approval letter",
            "final approval": "approval letter",
            "gop": "approval letter",
            "guarantee of payment": "approval letter",
            "referral letter": "approval letter",
            "approval referral letter gop": "approval letter",
            "discharge summary": "discharge summary",
            "death summary": "death summary",
            "transfer summary": "transfer summary",
            "final hospital bill": "final bill",
            "hospital final bill": "final bill",
            "detailed final bill": "final bill",
            "bill summary": "final bill",
        }

        return aliases.get(text, text)

    def summary(self) -> dict[str, Any]:
        return {
            "documentCount": len(self._documents),
            "documentTypes": self.document_types(),
        }

    def _build_documents(
        self,
    ) -> list[ManifestDocument]:
        raw_documents = self._extract_document_list()

        documents: list[ManifestDocument] = []

        for item in raw_documents:
            if not isinstance(item, dict):
                continue

            document_type = str(
                self._first_value(
                    item,
                    self.DOCUMENT_TYPE_KEYS,
                )
                or ""
            ).strip()

            if not document_type:
                continue

            file_name_value = self._first_value(
                item,
                self.FILE_NAME_KEYS,
            )

            confidence_value = self._first_value(
                item,
                self.CONFIDENCE_KEYS,
            )

            documents.append(
                ManifestDocument(
                    document_type=document_type,
                    normalized_document_type=(
                        self.normalize_document_type(
                            document_type
                        )
                    ),
                    file_name=(
                        str(file_name_value).strip()
                        if file_name_value is not None
                        else None
                    ),
                    page_numbers=self._extract_page_numbers(
                        item
                    ),
                    confidence=self._to_float(
                        confidence_value
                    ),
                    raw=item,
                )
            )

        return documents

    def _extract_document_list(
        self,
    ) -> list[dict[str, Any]]:
        for key in self.DOCUMENT_LIST_KEYS:
            value = self._manifest.get(key)

            if isinstance(value, list):
                return value

        packet = self._manifest.get("packet")

        if isinstance(packet, dict):
            for key in self.DOCUMENT_LIST_KEYS:
                value = packet.get(key)

                if isinstance(value, list):
                    return value

        result = self._manifest.get("result")

        if isinstance(result, dict):
            for key in self.DOCUMENT_LIST_KEYS:
                value = result.get(key)

                if isinstance(value, list):
                    return value

        return []

    @classmethod
    def _matches_document_type(
        cls,
        *,
        required_type: str,
        actual_type: str,
    ) -> bool:
        if not required_type or not actual_type:
            return False

        if required_type == actual_type:
            return True

        required_tokens = set(required_type.split())
        actual_tokens = set(actual_type.split())

        if not required_tokens or not actual_tokens:
            return False

        return required_tokens.issubset(
            actual_tokens
        ) or actual_tokens.issubset(
            required_tokens
        )

    @staticmethod
    def _first_value(
        item: dict[str, Any],
        keys: tuple[str, ...],
    ) -> Any:
        for key in keys:
            value = item.get(key)

            if value is not None and value != "":
                return value

        return None

    @classmethod
    def _extract_page_numbers(
        cls,
        item: dict[str, Any],
    ) -> list[int]:
        value = cls._first_value(
            item,
            cls.PAGE_NUMBER_KEYS,
        )

        if value is None:
            return []

        if isinstance(value, int):
            return [value]

        if isinstance(value, list):
            pages: list[int] = []

            for page in value:
                try:
                    pages.append(int(page))
                except (TypeError, ValueError):
                    continue

            return pages

        try:
            return [int(value)]
        except (TypeError, ValueError):
            return []

    @staticmethod
    def _to_float(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None