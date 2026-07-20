from datetime import datetime

from pydantic import BaseModel, Field


class ActivityLogCreateRequest(BaseModel):
    username: str | None = Field(default=None, max_length=100)
    action_type: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=200)
    details: str | None = Field(default=None, max_length=1000)


class ActivityLogItem(BaseModel):
    id: int
    username: str | None
    action_type: str
    target: str
    details: str | None
    ip_address: str | None
    timestamp: datetime

    class Config:
        from_attributes = True


class ActivityLogListResponse(BaseModel):
    items: list[ActivityLogItem]
    total: int
