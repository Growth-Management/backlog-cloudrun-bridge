import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, ValidationError

from app.api.routes.issues import get_backlog_client
from app.clients.backlog_client import BacklogClient, BacklogClientError
from app.core.security import verify_bearer_token
from app.services.issues import get_issue, search_issues

MCP_PROTOCOL_VERSION = "2025-06-18"


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | None = None


class SearchIssuesArguments(BaseModel):
    keyword: str | None = Field(default=None, min_length=1)
    status_ids: list[int] | None = None
    assignee_ids: list[int] | None = None
    count: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class GetIssueArguments(BaseModel):
    issue_key: str = Field(min_length=1, max_length=100)


router = APIRouter(
    prefix="/mcp",
    tags=["mcp"],
    dependencies=[Depends(verify_bearer_token)],
)


@router.post("", response_model=None)
def handle_mcp_request(
    payload: JsonRpcRequest,
    client: Annotated[BacklogClient, Depends(get_backlog_client)],
) -> dict[str, Any] | Response:
    if payload.jsonrpc != "2.0":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="jsonrpc must be 2.0",
        )

    if payload.id is None:
        return Response(status_code=status.HTTP_202_ACCEPTED)

    if payload.method == "initialize":
        return json_rpc_result(payload.id, initialize_result())
    if payload.method == "tools/list":
        return json_rpc_result(payload.id, {"tools": tool_definitions()})
    if payload.method == "tools/call":
        return json_rpc_result(payload.id, call_tool(client, payload.params or {}))

    return json_rpc_error(payload.id, -32601, f"Unknown method: {payload.method}")


def initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {
            "tools": {
                "listChanged": False,
            },
        },
        "serverInfo": {
            "name": "backlog-cloudrun-bridge",
            "title": "Backlog Cloud Run Bridge",
            "version": "0.1.0",
        },
        "instructions": (
            "Use these tools to read Backlog issues from the configured Backlog "
            "project. Write operations are not exposed by this MCP endpoint."
        ),
    }


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "backlog_search_issues",
            "title": "Search Backlog Issues",
            "description": "Search Backlog issues in the configured project.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Optional keyword to search in Backlog issues.",
                    },
                    "status_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional Backlog status IDs to filter by.",
                    },
                    "assignee_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional Backlog assignee IDs to filter by.",
                    },
                    "count": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 20,
                    },
                    "offset": {
                        "type": "integer",
                        "minimum": 0,
                        "default": 0,
                    },
                },
                "additionalProperties": False,
            },
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
            },
        },
        {
            "name": "backlog_get_issue",
            "title": "Get Backlog Issue",
            "description": "Get a Backlog issue by issue key.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "Backlog issue key, such as ICESAO_GENTASK-1.",
                    },
                },
                "required": ["issue_key"],
                "additionalProperties": False,
            },
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
            },
        },
    ]


def call_tool(client: BacklogClient, params: dict[str, Any]) -> dict[str, Any]:
    tool_name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return tool_error("Tool arguments must be an object")

    try:
        if tool_name == "backlog_search_issues":
            parsed = SearchIssuesArguments.model_validate(arguments)
            result = search_issues(
                client,
                keyword=parsed.keyword,
                status_ids=parsed.status_ids,
                assignee_ids=parsed.assignee_ids,
                count=parsed.count,
                offset=parsed.offset,
            )
            return tool_success(result)
        if tool_name == "backlog_get_issue":
            parsed = GetIssueArguments.model_validate(arguments)
            return tool_success(get_issue(client, parsed.issue_key))
    except ValidationError as exc:
        return tool_error("Invalid tool arguments", {"errors": exc.errors()})
    except BacklogClientError as exc:
        return tool_error(
            exc.message,
            {
                "error_code": exc.error_code,
                "upstream_status_code": exc.status_code,
            },
        )

    return tool_error(f"Unknown tool: {tool_name}")


def tool_success(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            }
        ],
        "isError": False,
    }


def tool_error(message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    data = {"message": message}
    if details:
        data.update(details)
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            }
        ],
        "isError": True,
    }


def json_rpc_result(request_id: int | str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def json_rpc_error(request_id: int | str, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }
