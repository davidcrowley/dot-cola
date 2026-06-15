from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.auth import is_authenticated, login, logout


router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.get("/auth/session")
def get_session(request: Request) -> dict[str, object]:
    return {
        "authenticated": is_authenticated(request),
    }


@router.post("/auth/login")
def post_login(payload: LoginRequest, response: Response) -> dict[str, object]:
    if not login(response, payload.username, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    return {
        "authenticated": True,
        "username": payload.username,
    }


@router.post("/auth/logout")
def post_logout(response: Response) -> dict[str, bool]:
    logout(response)
    return {"authenticated": False}
