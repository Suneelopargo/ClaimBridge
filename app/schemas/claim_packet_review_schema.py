from pydantic import BaseModel, Field, field_validator


class ReviewedDocumentGroupRequest(BaseModel):
    groupId: str | None = None
    documentType: str
    displayName: str | None = None
    pageNumbers: list[int] = Field(min_length=1)
    reviewerRemarks: str | None = None

    @field_validator("documentType")
    @classmethod
    def validate_document_type(
        cls,
        value: str,
    ) -> str:
        cleaned = str(value or "").strip().upper()

        if not cleaned:
            raise ValueError("documentType is required")

        return cleaned

    @field_validator("pageNumbers")
    @classmethod
    def validate_page_numbers(
        cls,
        value: list[int],
    ) -> list[int]:
        if not value:
            raise ValueError(
                "Every document group must contain at least one page"
            )

        if any(page_number < 1 for page_number in value):
            raise ValueError(
                "Page numbers must be greater than zero"
            )

        return value


class SaveClaimPacketReviewRequest(BaseModel):
    groups: list[ReviewedDocumentGroupRequest] = Field(
        min_length=1
    )
    unassignedPageNumbers: list[int] = Field(
        default_factory=list
    )
    reviewerRemarks: str | None = None
    confirmReview: bool = False