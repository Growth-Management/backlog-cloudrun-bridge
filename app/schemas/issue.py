from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class IssueCreateRequest(BaseModel):
    summary: str = Field(min_length=1, max_length=255)
    description: str | None = None
    issue_type_id: int | None = Field(default=None, gt=0)
    issue_type_name: str | None = Field(default=None, min_length=1)
    priority: Literal["high", "normal", "low"] = "normal"
    assignee_id: int | None = Field(default=None, gt=0)
    start_date: date | None = None
    due_date: date | None = None


class NamedValue(BaseModel):
    id: int | None = None
    name: str | None = None


class Assignee(BaseModel):
    id: int | None = None
    name: str | None = None
    user_id: str | None = None
    mail_address: str | None = None


class IssueResponse(BaseModel):
    issue_key: str | None = None
    summary: str | None = None
    description: str | None = None
    status: NamedValue | None = None
    priority: NamedValue | None = None
    assignee: Assignee | None = None


class IssueListResponse(BaseModel):
    issues: list[IssueResponse]
    count: int
    offset: int
