from fastapi import APIRouter, Depends, HTTPException, status

from app.clients.backlog_client import BacklogClient, BacklogClientError
from app.core.config import Settings, get_settings
from app.core.security import verify_bearer_token
from app.schemas.issue import IssueCreateRequest, IssueResponse
from app.services.issues import create_issue

router = APIRouter(
    prefix="/issues",
    tags=["issues"],
    dependencies=[Depends(verify_bearer_token)],
)


def get_backlog_client(settings: Settings = Depends(get_settings)) -> BacklogClient:
    return BacklogClient(settings)


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
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": exc.message,
                "error_code": exc.error_code,
                "upstream_status_code": exc.status_code,
            },
        ) from exc
