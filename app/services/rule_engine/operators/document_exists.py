# app/services/rule_engine/operators/document_exists.py

from __future__ import annotations

from typing import Any

from app.services.rule_engine.manifest_accessor import (
    ManifestAccessor,
)
from app.services.rule_engine.models import (
    ClaimValidationContext,
    OperatorResult,
    RuleDefinition,
)
from app.services.rule_engine.operators.base import (
    BaseRuleOperator,
)


class DocumentExistsOperator(BaseRuleOperator):

    def execute(
        self,
        *,
        rule: RuleDefinition,
        context: ClaimValidationContext,
        manifest: ManifestAccessor,
    ) -> OperatorResult:
        required_document_types = (
            self._resolve_required_document_types(rule)
        )

        if not required_document_types:
            return OperatorResult(
                status="MANUAL_REVIEW",
                message=(
                    "No required document types are configured "
                    "for this rule."
                ),
                evidence={
                    "ruleCode": rule.rule_code,
                    "validationExpression": (
                        rule.validation_expression
                    ),
                    "mappedDocumentTypes": (
                        rule.required_document_types
                    ),
                    "manifest": manifest.summary(),
                },
                review_required=True,
            )

        match_mode = str(
            rule.validation_expression.get(
                "matchMode",
                "ALL",
            )
        ).strip().upper()

        if match_mode not in {"ALL", "ANY"}:
            return OperatorResult(
                status="MANUAL_REVIEW",
                message=(
                    f"Unsupported document match mode: "
                    f"{match_mode}"
                ),
                evidence={
                    "ruleCode": rule.rule_code,
                    "matchMode": match_mode,
                },
                review_required=True,
            )

        found_documents: list[dict[str, Any]] = []
        missing_document_types: list[str] = []

        for required_type in required_document_types:
            matching_documents = (
                manifest.find_documents(required_type)
            )

            if not matching_documents:
                missing_document_types.append(
                    required_type
                )
                continue

            found_documents.append(
                {
                    "requiredDocumentType": required_type,
                    "matches": [
                        {
                            "documentType": (
                                document.document_type
                            ),
                            "fileName": document.file_name,
                            "pageNumbers": (
                                document.page_numbers
                            ),
                            "confidence": (
                                document.confidence
                            ),
                        }
                        for document in matching_documents
                    ],
                }
            )

        if match_mode == "ALL":
            passed = not missing_document_types
        else:
            passed = bool(found_documents)

        if passed:
            return OperatorResult(
                status="PASS",
                message=(
                    rule.success_message
                    or self._success_message(
                        match_mode=match_mode,
                        found_count=len(
                            found_documents
                        ),
                        required_count=len(
                            required_document_types
                        ),
                    )
                ),
                evidence={
                    "ruleCode": rule.rule_code,
                    "operator": "DOCUMENT_EXISTS",
                    "matchMode": match_mode,
                    "requiredDocumentTypes": (
                        required_document_types
                    ),
                    "foundDocuments": found_documents,
                    "missingDocumentTypes": (
                        missing_document_types
                    ),
                    "manifestDocumentTypes": (
                        manifest.document_types()
                    ),
                },
                review_required=False,
            )

        return OperatorResult(
            status="FAIL",
            message=(
                rule.failure_message
                or self._failure_message(
                    match_mode=match_mode,
                    missing_document_types=(
                        missing_document_types
                    ),
                )
            ),
            evidence={
                "ruleCode": rule.rule_code,
                "operator": "DOCUMENT_EXISTS",
                "matchMode": match_mode,
                "requiredDocumentTypes": (
                    required_document_types
                ),
                "foundDocuments": found_documents,
                "missingDocumentTypes": (
                    missing_document_types
                ),
                "manifestDocumentTypes": (
                    manifest.document_types()
                ),
            },
            review_required=False,
        )

    @staticmethod
    def _resolve_required_document_types(
        rule: RuleDefinition,
    ) -> list[str]:
        expression = rule.validation_expression or {}

        configured_types = (
            expression.get("documentTypes")
            or expression.get("requiredDocumentTypes")
            or expression.get("documentType")
            or []
        )

        if isinstance(configured_types, str):
            configured_types = [configured_types]

        if not isinstance(configured_types, list):
            configured_types = []

        combined_values = [
            *configured_types,
            *rule.required_document_types,
        ]

        unique_values: list[str] = []
        seen: set[str] = set()

        for value in combined_values:
            text = str(value or "").strip()

            if not text:
                continue

            normalized = (
                ManifestAccessor.normalize_document_type(
                    text
                )
            )

            if normalized in seen:
                continue

            seen.add(normalized)
            unique_values.append(text)

        return unique_values

    @staticmethod
    def _success_message(
        *,
        match_mode: str,
        found_count: int,
        required_count: int,
    ) -> str:
        if match_mode == "ANY":
            return (
                f"At least one required document was found "
                f"({found_count} of {required_count})."
            )

        return (
            f"All {required_count} required document types "
            "were found."
        )

    @staticmethod
    def _failure_message(
        *,
        match_mode: str,
        missing_document_types: list[str],
    ) -> str:
        if match_mode == "ANY":
            return (
                "None of the configured document types "
                "were found."
            )

        return (
            "Missing required document types: "
            + ", ".join(missing_document_types)
        )