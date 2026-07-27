# app/services/sweet_engine/evaluation/metrics.py

from __future__ import annotations

from app.services.sweet_engine.evaluation.models import (
    EvaluationMetrics,
    PacketGroundTruth,
    PageEvaluationResult,
)
from app.services.sweet_engine.page_inventory import PageInventory


def calculate_evaluation_metrics(
    packet_id: str,
    inventory: PageInventory,
    ground_truth: PacketGroundTruth,
    results: list[PageEvaluationResult],
) -> EvaluationMetrics:
    total_pages = max(
        inventory.total_pages,
        len(ground_truth.pages),
    )

    evaluated_pages = len(results)

    correctly_classified = sum(
        1
        for result in results
        if result.classification_correct
    )

    incorrectly_classified = (
        evaluated_pages - correctly_classified
    )

    initially_uncertain = sum(
        1
        for result in results
        if result.initially_uncertain
    )

    context_recovered = [
        result
        for result in results
        if result.context_recovered
    ]

    correctly_recovered = sum(
        1
        for result in context_recovered
        if result.classification_correct
    )

    incorrectly_recovered = (
        len(context_recovered)
        - correctly_recovered
    )

    final_review_pages = sum(
        1
        for result in results
        if result.review_required
    )

    boundary_results = [
        result
        for result in results
        if result.boundary_correct is not None
    ]

    correctly_detected_boundaries = sum(
        1
        for result in boundary_results
        if result.boundary_correct is True
    )

    inventory_numbers = {
        page.page_number
        for page in inventory.pages
    }

    truth_numbers = {
        page.page_number
        for page in ground_truth.pages
    }

    missing_inventory_pages = len(
        truth_numbers - inventory_numbers
    )

    missing_ground_truth_pages = len(
        inventory_numbers - truth_numbers
    )

    integrity_errors = (
        inventory.validate_no_page_drop()
    )

    return EvaluationMetrics(
        packet_id=packet_id,
        total_pages=total_pages,
        evaluated_pages=evaluated_pages,
        missing_ground_truth_pages=(
            missing_ground_truth_pages
        ),
        missing_inventory_pages=(
            missing_inventory_pages
        ),
        correctly_classified_pages=(
            correctly_classified
        ),
        incorrectly_classified_pages=(
            incorrectly_classified
        ),
        classification_accuracy_percent=_percent(
            correctly_classified,
            evaluated_pages,
        ),
        initially_uncertain_pages=(
            initially_uncertain
        ),
        context_recovered_pages=len(
            context_recovered
        ),
        correctly_context_recovered_pages=(
            correctly_recovered
        ),
        incorrectly_context_recovered_pages=(
            incorrectly_recovered
        ),
        context_recovery_rate_percent=_percent(
            len(context_recovered),
            initially_uncertain,
        ),
        context_recovery_precision_percent=_percent(
            correctly_recovered,
            len(context_recovered),
        ),
        false_auto_recovery_rate_percent=_percent(
            incorrectly_recovered,
            len(context_recovered),
        ),
        final_review_pages=final_review_pages,
        human_review_rate_percent=_percent(
            final_review_pages,
            evaluated_pages,
        ),
        review_reduction_percent=_percent(
            initially_uncertain - final_review_pages,
            initially_uncertain,
        ),
        boundary_evaluated_pages=len(
            boundary_results
        ),
        correctly_detected_boundaries=(
            correctly_detected_boundaries
        ),
        boundary_accuracy_percent=_percent(
            correctly_detected_boundaries,
            len(boundary_results),
        ),
        dropped_pages=max(
            0,
            inventory.total_pages
            - len(inventory.pages),
        ),
        page_integrity_valid=not integrity_errors,
    )


def _percent(
    numerator: int,
    denominator: int,
) -> float:
    if denominator <= 0:
        return 0.0

    return round(
        numerator / denominator * 100,
        2,
    )