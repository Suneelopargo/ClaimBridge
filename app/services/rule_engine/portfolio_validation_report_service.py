from __future__ import annotations

import json
import logging

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import CLAIM_PACKET_SEGREGATED_DIR
from app.services.rule_engine.segregated_document_report_service import (
    SegregatedDocumentReportService,
)
from app.services.rule_engine.segregated_packet_inventory_service import (
    SegregatedPacketInventoryService,
)


logger = logging.getLogger(__name__)


class PortfolioValidationReportService:
    def __init__(
        self,
        inventory_service: (
            SegregatedPacketInventoryService
            | None
        ) = None,
        report_service: (
            SegregatedDocumentReportService
            | None
        ) = None,
        output_root: Path | None = None,
    ) -> None:
        self.inventory_service = (
            inventory_service
            or SegregatedPacketInventoryService()
        )

        self.report_service = (
            report_service
            or SegregatedDocumentReportService(
                inventory_service=(
                    self.inventory_service
                )
            )
        )

        self.output_root = (
            output_root
            or CLAIM_PACKET_SEGREGATED_DIR.parent
            / "validation-reports"
        )

    def generate_all(
        self,
    ) -> dict[str, Any]:
        inventory_items = (
            self.inventory_service
            .list_claim_packets()
        )

        generated_at = (
            datetime.now().isoformat()
        )

        claim_reports: list[
            dict[str, Any]
        ] = []

        errors: list[
            dict[str, str]
        ] = []

        for item in inventory_items:
            try:
                report = (
                    self.report_service
                    .generate_report(
                        item.claim_id
                    )
                )

                report_dict = (
                    report.to_dict()
                )

                self._persist_claim_copy(
                    claim_id=item.claim_id,
                    report=report_dict,
                )

                claim_reports.append(
                    report_dict
                )

            except Exception as exc:
                logger.exception(
                    "Unable to generate "
                    "validation report for %s",
                    item.claim_id,
                )

                errors.append(
                    {
                        "claimId": (
                            item.claim_id
                        ),
                        "error": str(exc),
                    }
                )

        portfolio = (
            self._build_portfolio_report(
                claim_reports=claim_reports,
                errors=errors,
                generated_at=generated_at,
            )
        )

        self._persist_portfolio(
            portfolio
        )

        return portfolio

    def _build_portfolio_report(
        self,
        *,
        claim_reports: list[
            dict[str, Any]
        ],
        errors: list[
            dict[str, str]
        ],
        generated_at: str,
    ) -> dict[str, Any]:
        claim_summaries: list[
            dict[str, Any]
        ] = []

        overall_rule_review_counts: (
            Counter[int]
        ) = Counter()

        overall_rule_fail_counts: (
            Counter[int]
        ) = Counter()

        total_documents = 0
        total_pass = 0
        total_fail = 0
        total_review = 0
        total_na = 0
        total_applicable = 0
        total_decided = 0

        for report in claim_reports:
            summary = (
                report.get("summary")
                or {}
            )

            insights = (
                report.get("insights")
                or {}
            )

            documents = (
                report.get("documents")
                or []
            )

            total_documents += len(
                documents
            )

            pass_count = int(
                summary.get(
                    "passCount",
                    0,
                )
            )
            fail_count = int(
                summary.get(
                    "failCount",
                    0,
                )
            )
            review_count = int(
                summary.get(
                    "reviewCount",
                    0,
                )
            )
            na_count = int(
                summary.get(
                    "naCount",
                    0,
                )
            )
            applicable = int(
                summary.get(
                    "applicableRules",
                    0,
                )
            )

            decided = (
                pass_count
                + fail_count
            )

            total_pass += pass_count
            total_fail += fail_count
            total_review += (
                review_count
            )
            total_na += na_count
            total_applicable += (
                applicable
            )
            total_decided += decided

            for item in (
                insights.get(
                    "mostUncertainRules"
                )
                or []
            ):
                rule_number = int(
                    item.get(
                        "ruleNumber",
                        0,
                    )
                )

                overall_rule_review_counts[
                    rule_number
                ] += int(
                    item.get(
                        "count",
                        0,
                    )
                )

            for item in (
                insights.get(
                    "mostFailedRules"
                )
                or []
            ):
                rule_number = int(
                    item.get(
                        "ruleNumber",
                        0,
                    )
                )

                overall_rule_fail_counts[
                    rule_number
                ] += int(
                    item.get(
                        "count",
                        0,
                    )
                )

            claim_summaries.append(
                {
                    "claimId": report.get(
                        "claimId"
                    ),
                    "patientName": (
                        report.get(
                            "patientName"
                        )
                    ),
                    "payerCode": report.get(
                        "payerCode"
                    ),
                    "documentCount": len(
                        documents
                    ),
                    "passCount": (
                        pass_count
                    ),
                    "failCount": (
                        fail_count
                    ),
                    "reviewCount": (
                        review_count
                    ),
                    "naCount": na_count,
                    "confirmedReadinessPercent": (
                        summary.get(
                            "readinessPercent",
                            0,
                        )
                    ),
                    "decisionCoveragePercent": (
                        summary.get(
                            "decisionCoveragePercent",
                            0,
                        )
                    ),
                    "humanReviewBurdenPercent": (
                        summary.get(
                            "reviewPercent",
                            0,
                        )
                    ),
                    "overallStatus": (
                        insights.get(
                            "overallStatus"
                        )
                    ),
                }
            )

        confirmed_readiness = (
            round(
                total_pass
                / total_decided
                * 100,
                2,
            )
            if total_decided
            else 0.0
        )

        decision_coverage = (
            round(
                total_decided
                / total_applicable
                * 100,
                2,
            )
            if total_applicable
            else 0.0
        )

        human_review_burden = (
            round(
                total_review
                / total_applicable
                * 100,
                2,
            )
            if total_applicable
            else 0.0
        )

        claim_summaries.sort(
            key=lambda item: (
                -item[
                    "failCount"
                ],
                -item[
                    "reviewCount"
                ],
                item[
                    "decisionCoveragePercent"
                ],
            )
        )

        rule_lookup = self._rule_lookup(
            claim_reports
        )

        return {
            "generatedAt": generated_at,
            "reportType": (
                "HCG_CLAIM_VALIDATION_PORTFOLIO"
            ),
            "ruleSet": {
                "name": (
                    "HCG Document "
                    "Validation MVP"
                ),
                "version": "MVP-1.0",
                "configuredRuleCount": 28,
                "catalogueRuleCount": 72,
            },
            "summary": {
                "totalClaimsDiscovered": (
                    len(
                        claim_reports
                    )
                    + len(errors)
                ),
                "successfulClaims": len(
                    claim_reports
                ),
                "failedClaims": len(
                    errors
                ),
                "totalDocuments": (
                    total_documents
                ),
                "applicableChecks": (
                    total_applicable
                ),
                "passCount": total_pass,
                "failCount": total_fail,
                "reviewCount": (
                    total_review
                ),
                "naCount": total_na,
                "confirmedReadinessPercent": (
                    confirmed_readiness
                ),
                "decisionCoveragePercent": (
                    decision_coverage
                ),
                "humanReviewBurdenPercent": (
                    human_review_burden
                ),
            },
            "claims": claim_summaries,
            "portfolioInsights": {
                "claimsWithFailures": sum(
                    item["failCount"] > 0
                    for item
                    in claim_summaries
                ),
                "claimsRequiringReview": sum(
                    item[
                        "reviewCount"
                    ] > 0
                    for item
                    in claim_summaries
                ),
                "claimsFullyDecided": sum(
                    item[
                        "reviewCount"
                    ] == 0
                    for item
                    in claim_summaries
                ),
                "mostFailedRules": [
                    {
                        "ruleNumber": (
                            rule_number
                        ),
                        "ruleName": (
                            rule_lookup.get(
                                rule_number,
                                (
                                    "Rule "
                                    f"{rule_number}"
                                ),
                            )
                        ),
                        "count": count,
                    }
                    for (
                        rule_number,
                        count,
                    )
                    in (
                        overall_rule_fail_counts
                        .most_common(10)
                    )
                ],
                "mostUncertainRules": [
                    {
                        "ruleNumber": (
                            rule_number
                        ),
                        "ruleName": (
                            rule_lookup.get(
                                rule_number,
                                (
                                    "Rule "
                                    f"{rule_number}"
                                ),
                            )
                        ),
                        "count": count,
                    }
                    for (
                        rule_number,
                        count,
                    )
                    in (
                        overall_rule_review_counts
                        .most_common(10)
                    )
                ],
                "priorityClaims": (
                    claim_summaries[:10]
                ),
            },
            "errors": errors,
        }

    @staticmethod
    def _rule_lookup(
        claim_reports: list[
            dict[str, Any]
        ],
    ) -> dict[int, str]:
        lookup: dict[
            int,
            str,
        ] = {}

        for report in claim_reports:
            for rule in (
                report.get("rules")
                or []
            ):
                try:
                    rule_number = int(
                        rule.get(
                            "ruleNumber"
                        )
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    continue

                lookup[rule_number] = str(
                    rule.get(
                        "ruleName"
                    )
                    or (
                        f"Rule "
                        f"{rule_number}"
                    )
                )

        return lookup

    def _persist_claim_copy(
        self,
        *,
        claim_id: str,
        report: dict[str, Any],
    ) -> None:
        claim_directory = (
            self.output_root
            / "claims"
            / claim_id
        )

        claim_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        path = (
            claim_directory
            / "document_validation_report.json"
        )

        with path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                report,
                file,
                indent=2,
                ensure_ascii=False,
            )

    def _persist_portfolio(
        self,
        portfolio: dict[str, Any],
    ) -> None:
        portfolio_directory = (
            self.output_root
            / "portfolio"
        )

        portfolio_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        path = (
            portfolio_directory
            / "portfolio_validation_report.json"
        )

        with path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                portfolio,
                file,
                indent=2,
                ensure_ascii=False,
            )