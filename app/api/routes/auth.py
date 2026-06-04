from fastapi import APIRouter, Depends

from app.core.security import verify_bearer_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/check", dependencies=[Depends(verify_bearer_token)])
def check_auth() -> dict[str, str]:
    return {"status": "ok"}
