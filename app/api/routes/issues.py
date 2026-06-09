from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.clients.backlog_client import BacklogClient, BacklogClientError
from app.core.config import Settings, get_settings
from app.core.security import verify_bearer_token
from app.schemas.issue import (
    IssueCreateRequest,
    IssueListResponse,
    IssueResponse,
    IssueUpdateRequest,
)
from app.services.issues import create_issue, get_issue, search_issues, update_issue

router = APIRouter(
    prefix="/issues",
    tags=["issues"],
    dependencies=[Depends(verify_bearer_token)],
)


def get_backlog_client(settings: Settings = Depends(get_settings)) -> BacklogClient:
    return BacklogClient(settings)


def raise_upstream_error(exc: BacklogClientError) -> None:
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "message": exc.message,
            "error_code": exc.error_code,
            "upstream_status_code": exc.status_code,
        },
    ) from exc


@router.get("", response_model=IssueListResponse)
def list_backlog_issues(
    keyword: str | None = None,
    status_id: Annotated[list[int] | None, Query()] = None,
    assignee_id: Annotated[list[int] | None, Query()] = None,
    count: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    client: BacklogClient = Depends(get_backlog_client),
) -> dict:
    try:
        return search_issues(
            client,
            keyword=keyword,
            status_ids=status_id,
            assignee_ids=assignee_id,
            count=count,
            offset=offset,
        )
    except BacklogClientError as exc:
        raise_upstream_error(exc)


@router.get("/{issue_key}", response_model=IssueResponse)
def get_backlog_issue(
    issue_key: str,
    client: BacklogClient = Depends(get_backlog_client),
) -> dict:
    try:
        return get_issue(client, issue_key)
    except BacklogClientError as exc:
        raise_upstream_error(exc)


@router.post("", response_model=IssueResponse, status_code=status.HTTP_201_CREATED)
def create_backlog_issue(
    request: IssueCreateRequest,
    client: BacklogClient = Depends(get_backlog_client),
) -> dict:
    try:
        return create_issue(client, request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except BacklogClientError as exc:
        raise_upstream_error(exc)


@router.patch("/{issue_key}", response_model=IssueResponse)
def update_backlog_issue(
    issue_key: str,
    request: IssueUpdateRequest,
    client: BacklogClient = Depends(get_backlog_client),
) -> dict:
    try:
        return update_issue(client, issue_key, request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except BacklogClientError as exc:
        raise_upstream_error(exc)
