from app.clients.backlog_client import BacklogClient
from app.schemas.issue import IssueCreateRequest


PRIORITY_IDS = {
    "high": 2,
    "normal": 3,
    "low": 4,
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
