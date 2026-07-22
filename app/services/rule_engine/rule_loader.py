from __future__ import annotations

from datetime import date

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload

from app.models.validation_rule import ValidationRule
from app.models.validation_rule_version import ValidationRuleVersion
from app.services.rule_engine.models import RuleDefinition


class RuleLoader:
    def __init__(self, db: Session):
        self.db = db

    def load_published_rules(
        self,
        *,
        as_of_date: date | None = None,
        payer_code: str | None = None,
    ) -> list[RuleDefinition]:
        effective_date = as_of_date or date.today()
        print("=" * 60)
        print("Loading rules")
        print(f"Payer : {payer_code}")
        print("=" * 60)
        rows = (
            self.db.query(
                ValidationRule,
                ValidationRuleVersion,
            )
            .join(
                ValidationRuleVersion,
                ValidationRuleVersion.rule_id
                == ValidationRule.id,
            )
            .options(
                joinedload(
                    ValidationRule.document_types
                )
            )
            .filter(
                ValidationRule.is_active.is_(True),
                ValidationRuleVersion.is_published.is_(True),
                ValidationRuleVersion.effective_from
                <= effective_date,
                or_(
                    ValidationRuleVersion.effective_to.is_(None),
                    ValidationRuleVersion.effective_to
                    >= effective_date,
                ),
            )
            .order_by(
                ValidationRule.rule_code.asc(),
                ValidationRuleVersion.version_number.desc(),
            )
            .all()
        )

        latest_by_rule: dict[int, RuleDefinition] = {}

        for rule, version in rows:
            if rule.id in latest_by_rule:
                continue

            applicability = (
                version.applicability_expression or {}
            )

            if not self._payer_may_apply(
                applicability_expression=applicability,
                payer_code=payer_code,
            ):
                continue

            latest_by_rule[rule.id] = RuleDefinition(
                rule_id=rule.id,
                rule_code=rule.rule_code,
                rule_name=rule.rule_name,
                category=rule.category,
                rule_type=rule.rule_type,
                severity=rule.severity,
                rule_version_id=version.id,
                version_number=version.version_number,
                applicability_expression=applicability,
                validation_expression=(
                    version.validation_expression or {}
                ),
                success_message=version.success_message,
                failure_message=version.failure_message,
                required_document_types=[
                    mapping.document_type
                    for mapping in rule.document_types
                    if mapping.is_mandatory
                ],
            )
        print(f"Loaded {len(latest_by_rule)} rules")
        return list(latest_by_rule.values())

    @staticmethod
    def _payer_may_apply(
        *,
        applicability_expression: dict,
        payer_code: str | None,
    ) -> bool:
        """
        Preliminary filtering only.

        Full applicability is still evaluated later. A rule is retained
        when no payer restriction is defined or payer information is not
        available.
        """

        payer_types = applicability_expression.get(
            "payerTypes"
        )

        if not payer_types:
            return True

        if not payer_code:
            return True

        normalized_payer = payer_code.strip().upper()

        return normalized_payer in {
            str(item).strip().upper()
            for item in payer_types
        }