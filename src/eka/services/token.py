import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import jwt
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from eka.config import get_settings
from eka.db.models import RefreshToken
from eka.repositories.token import create_refresh_token, get_refresh_token
from eka.schemas.token import TokenPair, TokenPayload

# Claims, которые additional_data не может перезаписать
_RESERVED_CLAIMS = frozenset({"sub", "exp", "iat", "nbf", "jti", "type"})


@lru_cache(maxsize=1)
def _private_key() -> str:
    return get_settings().JWT_PRIVATE_KEY_PATH.read_text()


@lru_cache(maxsize=1)
def _public_key() -> str:
    return get_settings().JWT_PUBLIC_KEY_PATH.read_text()


def create_token(
    subject: str,
    token_type: str = "access",
    expires_delta: timedelta | None = None,
    additional_data: dict[str, Any] | None = None,
) -> str:
    """
    Создаёт подписанный JWT.

    Args:
            subject:         ID пользователя (str UUID)
            token_type:      "access" или "refresh" — сохраняется в payload,
                                                    проверяется при decode
            expires_delta:   Время жизни; если None — берётся из settings
            additional_data: Доп. claims (роль, tenant_id и т.д.).
                                                    Зарезервированные claims игнорируются.
    """

    if not subject:
        raise ValueError("Subject cannot be empty")

    if token_type not in ("access", "refresh"):
        raise ValueError(f"Unknown token_type: {token_type!r}")

    settings = get_settings()

    if expires_delta is None:
        seconds = (
            settings.ACCESS_TOKEN_EXPIRE_SECONDS
            if token_type == "access"
            else settings.REFRESH_TOKEN_EXPIRE_SECONDS
        )
        expires_delta = timedelta(seconds=seconds)

    now = datetime.now(UTC)

    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "exp": now + expires_delta,
        "iat": now,
        "nbf": now,
        "jti": str(uuid.uuid4()),
    }

    if additional_data:
        safe = {k: v for k, v in additional_data.items() if k not in _RESERVED_CLAIMS}
        payload.update(safe)

    return jwt.encode(payload, _private_key(), algorithm=settings.JWT_ALG)


def decode_token(token: str, expected_type: str = "access") -> TokenPayload:
    """
    Декодирует JWT и проверяет:
    - подпись
    - срок действия (exp / nbf)
    - тип токена (access / refresh)

    Args:
            token:         Сырой JWT-строка
            expected_type: "access" или "refresh".
                                            Передача refresh-токена туда, где ожидается access,
                                            вернёт 401 — это намеренная защита.
    """

    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            _public_key(),
            algorithms=[settings.JWT_ALG],
            leeway=timedelta(seconds=10),
        )

    except jwt.ExpiredSignatureError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err

    except jwt.InvalidTokenError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err

    if payload.get("type") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Expected {expected_type} token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenPayload.model_validate(payload)


def create_token_pair(
    user_id: uuid.UUID, additional_data: dict[str, Any] | None = None
) -> TokenPair:
    """Создаёт access + refresh токены для пользователя."""
    settings = get_settings()

    access_token = create_token(
        subject=str(user_id),
        token_type="access",
        additional_data=additional_data,
    )

    refresh_token = create_token(
        subject=str(user_id), additional_data=additional_data, token_type="refresh"
    )

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        token_type="Bearer",
    )


async def save_refresh_token(
    db: AsyncSession,
    user_id: uuid.UUID,
    refresh_token: str,
) -> RefreshToken:
    """
    Сохраняет refresh token в БД.
    """
    return await create_refresh_token(db, user_id, refresh_token)


async def refresh_access_token(
    db: AsyncSession,
    refresh_token: str,
    additional_data: dict[str, Any] | None = None,
) -> TokenPair:
    """
    Обновляет пару токенов по refresh-токену.
    """

    payload = decode_token(refresh_token, expected_type="refresh")
    db_token = await get_refresh_token(
        db=db,
        token=refresh_token,
    )

    if db_token is None:
        raise HTTPException(
            status_code=401,
            detail="Refresh token not found",
        )

    if db_token.revoked:
        raise HTTPException(
            status_code=401,
            detail="Refresh token revoked",
        )

    db_token.revoked = True

    new_tokens = create_token_pair(
        user_id=uuid.UUID(payload.sub),
        additional_data=additional_data,
    )

    await create_refresh_token(
        db=db,
        user_id=uuid.UUID(payload.sub),
        token=new_tokens.refresh_token,
    )

    return new_tokens
