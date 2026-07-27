# app/services/sweet_engine/evidence_resolver.py

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.sweet_engine.enums import ClassificationSource
from app.services.sweet_engine.models import PageInventoryItem
from app.services.sweet_engine.page_inventory import PageInventory
from app.services.sweet_engine.rule_priority import EvidenceRulePriority


@dataclass
class EvidenceResolutionDecision:
    page_number: int
    resolved: bool
    document_type: str = "UNKNOWN"
    confidence: float = 0.0
    rule_code: str = ""
    priority: EvidenceRulePriority = EvidenceRulePriority.STRONG_CONTENT
    reasons: list[str] = field(default_factory=list)
    may_override_classification: bool = True


class EvidenceResolver:
    """
    Resolve document types using high-precision page-local evidence.

    Important:
    - Rules classify the primary purpose of the document.
    - Treatment names appearing inside another document are metadata only.
    - Only an explicit treatment-order title can classify TREATMENT_ORDER.
    - Lower-priority evidence cannot replace stronger existing evidence.
    """

    def resolve_inventory(
        self,
        inventory: PageInventory,
    ) -> list[EvidenceResolutionDecision]:
        decisions: list[EvidenceResolutionDecision] = []

        for page in inventory.pages:
            decision = self.resolve_page(page)
            decisions.append(decision)

            if not decision.resolved:
                continue

            page.evidence.custom_features.setdefault(
                "evidenceDecisions",
                [],
            ).append({
                "ruleCode": decision.rule_code,
                "documentType": decision.document_type,
                "confidence": decision.confidence,
                "priority": int(decision.priority),
                "priorityName": decision.priority.name,
                "mayOverrideClassification": (
                    decision.may_override_classification
                ),
                "reasons": decision.reasons,
            })

            if not self._should_apply_decision(page, decision):
                page.add_processing_note(
                    f"Evidence rule {decision.rule_code} did not "
                    "override the current classification because its "
                    f"priority {decision.priority.name} was not stronger."
                )
                continue

            previous_type = page.final_document_type

            page.resolve_classification(
                document_type=decision.document_type,
                confidence=decision.confidence,
                source=ClassificationSource.RULE,
                note=(
                    f"Evidence rule {decision.rule_code} "
                    f"[{decision.priority.name}]: "
                    + " ".join(decision.reasons)
                ),
            )

            page.evidence.custom_features.update({
                "evidenceRuleCode": decision.rule_code,
                "classificationPriority": int(decision.priority),
                "classificationPriorityName": decision.priority.name,
                "previousDocumentType": previous_type,
            })

            page.review.required = False
            page.review.reason_code = None
            page.review.message = ""
            page.review.suggested_action = ""
            page.review.alternatives = []

        return decisions

    def resolve_page(
        self,
        page: PageInventoryItem,
    ) -> EvidenceResolutionDecision:
        text = self._normalize_text(
            page.evidence.extracted_text
        )

        if not text:
            return self._not_resolved(page)

        # ---------------------------------------------------------
        # Explicit dispatch checklist
        # ---------------------------------------------------------
        if self._contains_any(
            text,
            "despatch checklist",
            "dispatch checklist",
        ):
            return self._resolved(
                page=page,
                document_type="CHECKLIST",
                confidence=0.99,
                rule_code="DISPATCH_CHECKLIST_TITLE",
                priority=EvidenceRulePriority.EXPLICIT_TITLE,
                reasons=[
                    "Visible dispatch checklist title detected."
                ],
            )

        # ---------------------------------------------------------
        # Explicit payment/deposit receipt
        # ---------------------------------------------------------
        if self._contains_any(
            text,
            "deposit receipt",
            "payment receipt",
        ) and self._contains_any(
            text,
            "transaction amount",
            "received with thanks",
            "mode of payment",
            "cashier",
        ):
            return self._resolved(
                page=page,
                document_type="PAYMENT_RECEIPT",
                confidence=0.99,
                rule_code="PAYMENT_RECEIPT_EXPLICIT_TITLE",
                priority=EvidenceRulePriority.EXPLICIT_TITLE,
                reasons=[
                    "Receipt title is visible.",
                    "Transaction and payment evidence is present.",
                ],
            )

        # ---------------------------------------------------------
        # Explicit cashless authorization title
        # Must run before content-only authorization detection.
        # ---------------------------------------------------------
        if self._contains_any(
            text,
            "cashless authorization letter",
        ):
            return self._resolved(
                page=page,
                document_type="CASHLESS_AUTHORIZATION_LETTER",
                confidence=0.99,
                rule_code="CASHLESS_AUTHORIZATION_TITLE",
                priority=EvidenceRulePriority.EXPLICIT_TITLE,
                reasons=[
                    "Explicit Cashless Authorization Letter title "
                    "detected."
                ],
            )

        # ---------------------------------------------------------
        # Explicit treatment-order title
        # Treatment names alone must never trigger this rule.
        # ---------------------------------------------------------
        treatment_subtype = (
            self._detect_explicit_treatment_order_subtype(text)
        )

        if treatment_subtype:
            page.evidence.custom_features.update({
                "documentFamily": "TREATMENT_ORDER",
                "documentSubtype": treatment_subtype,
            })

            return self._resolved(
                page=page,
                document_type="TREATMENT_ORDER",
                confidence=0.99,
                rule_code=(
                    f"{treatment_subtype}_EXPLICIT_ORDER_TITLE"
                ),
                priority=EvidenceRulePriority.EXPLICIT_TITLE,
                reasons=[
                    "Explicit treatment-order title detected."
                ],
            )

        # ---------------------------------------------------------
        # Covering/submission confirmation template
        #
        # This distinctive HCG submission document can override a
        # high-confidence CHECKLIST prediction because its primary
        # purpose is submission confirmation, not checklist control.
        # ---------------------------------------------------------
        if self._contains_all(
            text,
            "we hereby confirm",
            "claim number",
            "total bill amount",
        ) and self._contains_any(
            text,
            "couriered",
            "submitted to medi assist",
            "documents uploaded",
            "as per original claim documents",
        ):
            return self._resolved(
                page=page,
                document_type="COVERING_LETTER",
                confidence=0.97,
                rule_code="COVERING_LETTER_CONFIRMATION",
                priority=EvidenceRulePriority.EXPLICIT_TITLE,
                reasons=[
                    "Contains a distinctive submission confirmation "
                    "addressed to the payer or TPA.",
                    "Contains claim and bill summary details.",
                ],
            )

        # ---------------------------------------------------------
        # PAN / proposer KYC document
        # ---------------------------------------------------------
        if self._contains_all(
            text,
            "permanent account number",
            "income tax",
        ) or self._contains_all(
            text,
            "government of india",
            "permanent account number card",
        ):
            return self._resolved(
                page=page,
                document_type="PROPOSER_ID_PROOF",
                confidence=0.98,
                rule_code="PAN_CARD",
                priority=EvidenceRulePriority.DOCUMENT_STRUCTURE,
                reasons=[
                    "Permanent Account Number card detected."
                ],
            )

        # ---------------------------------------------------------
        # Authorization continuation/content page
        # ---------------------------------------------------------
        if self._contains_any(
            text,
            "terms and conditions for authorization",
            "authorization summary",
            "authorization remarks",
        ) and self._contains_any(
            text,
            "authorized amount",
            "cashless documents",
            "claim settlement",
            "total authorized amount",
        ):
            return self._resolved(
                page=page,
                document_type="CASHLESS_AUTHORIZATION_LETTER",
                confidence=0.95,
                rule_code="CASHLESS_AUTHORIZATION_CONTENT",
                priority=EvidenceRulePriority.STRONG_CONTENT,
                reasons=[
                    "Authorization terminology and cashless "
                    "settlement structure detected."
                ],
            )

        return self._not_resolved(page)

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = str(value or "").lower()
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    @staticmethod
    def _contains_all(
        text: str,
        *phrases: str,
    ) -> bool:
        return all(phrase in text for phrase in phrases)

    @staticmethod
    def _contains_any(
        text: str,
        *phrases: str,
    ) -> bool:
        return any(phrase in text for phrase in phrases)

    @staticmethod
    def _resolved(
        *,
        page: PageInventoryItem,
        document_type: str,
        confidence: float,
        rule_code: str,
        priority: EvidenceRulePriority,
        reasons: list[str],
        may_override_classification: bool = True,
    ) -> EvidenceResolutionDecision:
        return EvidenceResolutionDecision(
            page_number=page.page_number,
            resolved=True,
            document_type=document_type,
            confidence=confidence,
            rule_code=rule_code,
            priority=priority,
            reasons=reasons,
            may_override_classification=(
                may_override_classification
            ),
        )

    @staticmethod
    def _not_resolved(
        page: PageInventoryItem,
    ) -> EvidenceResolutionDecision:
        return EvidenceResolutionDecision(
            page_number=page.page_number,
            resolved=False,
        )

    @staticmethod
    def _current_classification_priority(
        page: PageInventoryItem,
    ) -> EvidenceRulePriority:
        stored_priority = page.evidence.custom_features.get(
            "classificationPriority"
        )

        if stored_priority is not None:
            try:
                return EvidenceRulePriority(
                    int(stored_priority)
                )
            except (TypeError, ValueError):
                pass

        if (
            page.final_document_type != "UNKNOWN"
            and page.confidence >= 0.90
        ):
            return EvidenceRulePriority.DOCUMENT_STRUCTURE

        if (
            page.final_document_type != "UNKNOWN"
            and page.confidence >= 0.70
        ):
            return EvidenceRulePriority.STRONG_CONTENT

        return EvidenceRulePriority.CONTEXT

    @staticmethod
    def _should_apply_decision(
        page: PageInventoryItem,
        decision: EvidenceResolutionDecision,
    ) -> bool:
        if not decision.resolved:
            return False

        if not decision.may_override_classification:
            return False

        if page.final_document_type == "UNKNOWN":
            return True

        if page.final_document_type == decision.document_type:
            return True

        current_priority = (
            EvidenceResolver._current_classification_priority(page)
        )

        return decision.priority > current_priority

    def _detect_explicit_treatment_order_subtype(
        self,
        text: str,
    ) -> str | None:
        if self._contains_any(
            text,
            "chemotherapy order form",
            "chemo therapy order form",
            "chemo-therapy order form",
        ):
            return "CHEMOTHERAPY"

        if self._contains_any(
            text,
            "radiotherapy order form",
            "radiation therapy order form",
        ):
            return "RADIATION_THERAPY"

        if self._contains_any(
            text,
            "surgical order form",
            "surgery order form",
        ):
            return "SURGERY"

        if self._contains_any(
            text,
            "treatment order form",
        ):
            return "GENERAL"

        return None
