from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from eka.deps import get_db_session
from eka.schemas.token import RefreshTokenRequest, TokenPair
from eka.services.auth import login_user
from eka.services.token import (
    create_token_pair,
    refresh_access_token,
    save_refresh_token,
)

auth_router = APIRouter()


@auth_router.post("/token")
async def login_user_endpoint(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenPair:
    """Ручка для входа пользователя по username/email и паролю
    с созданием access_token и обновлением информации о сессии"""
    user = await login_user(
        db=db,
        login=form_data.username,
        password=form_data.password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    tokens = create_token_pair(user_id=user.id)

    await save_refresh_token(
        db=db,
        user_id=user.id,
        refresh_token=tokens.refresh_token,
    )

    return tokens


@auth_router.post("/refresh")
async def refresh_token_endpoint(
    body: RefreshTokenRequest, db: Annotated[AsyncSession, Depends(get_db_session)]
) -> TokenPair:
    """
    Обновление access токена с помощью refresh токена
    """
    tokens_data = await refresh_access_token(
        db=db,
        refresh_token=body.refresh_token,
        additional_data=None,
    )

    return tokens_data
