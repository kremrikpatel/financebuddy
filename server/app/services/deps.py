"""Shared FastAPI dependencies."""
from __future__ import annotations

import uuid

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    exc = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated",
                        headers={"WWW-Authenticate": "Bearer"})
    if not token:
        raise exc
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise exc
        user_id = uuid.UUID(payload["sub"])
    except (pyjwt.PyJWTError, KeyError, ValueError):
        raise exc from None
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise exc
    return user


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


def client_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")[:300]
