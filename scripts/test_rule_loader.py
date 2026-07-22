from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app.models  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.services.rule_engine.rule_loader import (  # noqa: E402
    RuleLoader,
)


def main() -> None:
    db = SessionLocal()

    try:
        loader = RuleLoader(db)

        rules = loader.load_published_rules(
            payer_code="INSURANCE_TPA"
        )

        print(f"Published rules loaded: {len(rules)}")

        for rule in rules[:10]:
            print(
                rule.rule_code,
                rule.rule_name,
                rule.validation_expression.get(
                    "operator"
                ),
            )

    finally:
        db.close()


if __name__ == "__main__":
    main()