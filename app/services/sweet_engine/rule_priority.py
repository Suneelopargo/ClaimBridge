# app/services/sweet_engine/rule_priority.py

from enum import IntEnum


class EvidenceRulePriority(IntEnum):
    """
    Higher values represent stronger evidence.

    A lower-priority rule must never replace a higher-priority
    classification.
    """

    METADATA_ONLY = 10
    CONTEXT = 40
    STRONG_CONTENT = 60
    DOCUMENT_STRUCTURE = 80
    EXPLICIT_TITLE = 100