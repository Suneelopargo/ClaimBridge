from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app.models  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.validation_rule import ValidationRule  # noqa: E402
from app.models.validation_rule_version import (  # noqa: E402
    ValidationRuleVersion,
)


INITIAL_RULE_CODES = [
    "HCG-DOC-052",  # Claim form
    "HCG-DOC-058",  # Approval / authorization
    "HCG-DOC-059",  # Discharge summary
    "HCG-DOC-068",  # Final bill / detailed bill
]


def main() -> None:
    db = SessionLocal()

    try:
        rows = (
            db.query(
                ValidationRule,
                ValidationRuleVersion,
            )
            .join(
                ValidationRuleVersion,
                ValidationRuleVersion.rule_id
                == ValidationRule.id,
            )
            .filter(
                ValidationRule.rule_code.in_(
                    INITIAL_RULE_CODES
                ),
                ValidationRuleVersion.is_published.is_(False),
            )
            .order_by(
                ValidationRule.rule_code,
                ValidationRuleVersion.version_number.desc(),
            )
            .all()
        )

        latest_by_rule: dict[int, tuple] = {}

        for rule, version in rows:
            if rule.id not in latest_by_rule:
                latest_by_rule[rule.id] = (rule, version)

        found_codes = {
            rule.rule_code
            for rule, _ in latest_by_rule.values()
        }

        missing_codes = sorted(
            set(INITIAL_RULE_CODES) - found_codes
        )

        if missing_codes:
            raise RuntimeError(
                "Draft versions were not found for: "
                + ", ".join(missing_codes)
            )

        for rule, version in latest_by_rule.values():
            version.is_published = True

            if version.effective_from is None:
                version.effective_from = date.today()

            version.change_reason = (
                "Published for initial DOCUMENT_EXISTS "
                "operator integration test"
            )

            print(
                f"Publishing {rule.rule_code}: "
                f"{rule.rule_name} "
                f"(version {version.version_number})"
            )

        db.commit()

        print(
            f"Published {len(latest_by_rule)} initial rules."
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()