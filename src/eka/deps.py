from collections.abc import AsyncGenerator, Generator
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from eka.config import get_settings
from eka.core.rag.pipeline import RAGQueryPipeline
from eka.db.models import User, UserRole
from eka.db.pg import AsyncSessionLocal, SyncSessionLocal
from eka.repositories.user import get_user_by_id
from eka.services.token import decode_token

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/token")


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Получение сессии для работы с бд"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@contextmanager
def get_sync_db_session() -> Generator[Session, None, None]:
    with SyncSessionLocal() as session:
        yield session


async def get_user_id_from_token(token: str = Depends(oauth2_scheme)) -> UUID | None:
    """Получение user_id из Token"""
    token_data = decode_token(token)
    return UUID(token_data.sub)


async def get_user_by_token(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> User | None:
    """Получение текущего пользователя по Token"""
    token_data = decode_token(token)

    user = await get_user_by_id(user_id=UUID(token_data.sub), db=db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(*roles: UserRole):
    """
    Фабрика зависимостей: проверяет что у пользователя нужная роль.

    Использование:
        Depends(require_role(UserRole.admin))
        Depends(require_role(UserRole.admin, UserRole.superadmin))
    """

    async def _check(
        current_user: Annotated[User, Depends(get_user_by_token)],
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: {[r.value for r in roles]}",
            )
        return current_user

    return _check


def get_rag_pipeline(request: Request) -> RAGQueryPipeline:
    return request.app.state.rag_pipeline
