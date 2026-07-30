from pydantic import BaseModel, field_validator, model_validator


class ChecklistItemDecisionRequest(BaseModel):
    reviewerDecision: str
    reviewerRemarks: str | None = None

    @field_validator(
        "reviewerDecision",
        mode="before",
    )
    @classmethod
    def normalize_reviewer_decision(
        cls,
        value,
    ) -> str:
        cleaned = str(
            value or ""
        ).strip().upper()

        allowed_values = {
            "REQUIRED",
            "OPTIONAL",
            "NOT_APPLICABLE",
        }

        if cleaned not in allowed_values:
            raise ValueError(
                "reviewerDecision must be one of: "
                "REQUIRED, OPTIONAL, NOT_APPLICABLE"
            )

        return cleaned

    @field_validator(
        "reviewerRemarks",
        mode="before",
    )
    @classmethod
    def normalize_reviewer_remarks(
        cls,
        value,
    ) -> str | None:
        if value is None:
            return None

        cleaned = str(value).strip()

        return cleaned or None

    @model_validator(mode="after")
    def validate_decision_remarks(self):
        if (
            self.reviewerDecision
            in {
                "OPTIONAL",
                "NOT_APPLICABLE",
            }
            and not self.reviewerRemarks
        ):
            raise ValueError(
                "reviewerRemarks is required when "
                "reviewerDecision is OPTIONAL or "
                "NOT_APPLICABLE"
            )

        return self