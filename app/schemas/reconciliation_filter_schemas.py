from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field


class ReconciliationFilterCondition(BaseModel):
    field: str
    operator: Literal["eq", "in", "contains", "startsWith", "gte", "lte", "between", "isNull", "isNotNull"]
    value: Optional[Any] = None


class ReconciliationSearchRequest(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=200)
    filters: List[ReconciliationFilterCondition] = Field(default_factory=list)
    sort: List[dict] = Field(default_factory=list)
