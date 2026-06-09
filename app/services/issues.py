from app.clients.backlog_client import BacklogClient
from app.schemas.issue import IssueCreateRequest, IssueUpdateRequest


PRIORITY_IDS = {
    "high": 2,
    "normal": 3,
    "low": 4,
}

STATUS_IDS = {
    "open": 1,
    "in_progress": 2,
    "resolved": 3,
    "closed": 4,
}


def create_issue(
    client: BacklogClient,
    request: IssueCreateRequest,
) -> dict:
    issue_type_id = resolve_issue_type_id(
        client,
        issue_type_id=request.issue_type_id,
        issue_type_name=request.issue_type_name,
    )
    priority_id = PRIORITY_IDS[request.priority]

    return client.create_issue(
        summary=request.summary,
        description=request.description,
        issue_type_id=issue_type_id,
        priority_id=priority_id,
        assignee_id=request.assignee_id,
        start_date=request.start_date.isoformat() if request.start_date else None,
        due_date=request.due_date.isoformat() if request.due_date else None,
    )


def search_issues(
    client: BacklogClient,
    keyword: str | None,
    status_ids: list[int] | None,
    assignee_ids: list[int] | None,
    count: int,
    offset: int,
) -> dict:
    issues = client.search_issues(
        keyword=keyword,
        status_ids=status_ids,
        assignee_ids=assignee_ids,
        count=count,
        offset=offset,
    )
    return {
        "issues": issues,
        "count": len(issues),
        "offset": offset,
    }


def get_issue(client: BacklogClient, issue_key: str) -> dict:
    return client.get_issue(issue_key)


def update_issue(
    client: BacklogClient,
    issue_key: str,
    request: IssueUpdateRequest,
) -> dict:
    if not has_update_value(request):
        raise ValueError("At least one update field is required")

    return client.update_issue(
        issue_key=issue_key,
        summary=request.summary,
        description=request.description,
        status_id=resolve_status_id(request.status_id, request.status),
        priority_id=resolve_priority_id(request.priority_id, request.priority),
        assignee_id=request.assignee_id,
        start_date=request.start_date.isoformat() if request.start_date else None,
        due_date=request.due_date.isoformat() if request.due_date else None,
    )


def has_update_value(request: IssueUpdateRequest) -> bool:
    return any(
        value is not None
        for value in (
            request.summary,
            request.description,
            request.status_id,
            request.status,
            request.priority_id,
            request.priority,
            request.assignee_id,
            request.start_date,
            request.due_date,
        )
    )


def resolve_status_id(status_id: int | None, status_name: str | None) -> int | None:
    if status_id is not None:
        return status_id
    if status_name is None:
        return None
    return STATUS_IDS[status_name]


def resolve_priority_id(priority_id: int | None, priority_name: str | None) -> int | None:
    if priority_id is not None:
        return priority_id
    if priority_name is None:
        return None
    return PRIORITY_IDS[priority_name]


def resolve_issue_type_id(
    client: BacklogClient,
    issue_type_id: int | None,
    issue_type_name: str | None,
) -> int:
    if issue_type_id is not None:
        return issue_type_id
    if not issue_type_name:
        raise ValueError("issue_type_id or issue_type_name is required")

    issue_type_name_lower = issue_type_name.casefold()
    for issue_type in client.get_issue_types():
        if str(issue_type.get("name", "")).casefold() == issue_type_name_lower:
            issue_type_id_value = issue_type.get("id")
            if isinstance(issue_type_id_value, int):
                return issue_type_id_value

    raise ValueError(f"Unknown issue_type_name: {issue_type_name}")
