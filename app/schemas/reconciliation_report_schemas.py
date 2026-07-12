from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class ReconciliationReportSort(BaseModel):
    field: str
    direction: Literal["asc", "desc"] = "asc"


class ReconciliationReportExportRequest(BaseModel):
    report_name: Optional[str] = Field(default="Reconciliation Report", max_length=150)
    fields: List[str] = Field(min_length=1)
    filters: Dict[str, Any] = Field(default_factory=dict)
    sort: List[ReconciliationReportSort] = Field(default_factory=list)

    @field_validator("fields")
    @classmethod
    def clean_fields(cls, value):
        result, seen = [], set()
        for item in value:
            item = item.strip()
            if item and item not in seen:
                seen.add(item)
                result.append(item)
        if not result:
            raise ValueError("At least one report field is required")
        return result
