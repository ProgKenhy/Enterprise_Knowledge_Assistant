import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eka.config import get_settings
from eka.db.models import RefreshToken


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_refresh_token(
    db: AsyncSession,
    user_id: UUID,
    token: str,
) -> RefreshToken:
    refresh = RefreshToken(
        user_id=user_id,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC)
        + timedelta(seconds=get_settings().REFRESH_TOKEN_EXPIRE_SECONDS),
    )

    db.add(refresh)
    await db.commit()
    await db.refresh(refresh)

    return refresh


async def get_refresh_token(db: AsyncSession, token: str):
    token_hash = hash_token(token)

    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))

    return result.scalar_one_or_none()
