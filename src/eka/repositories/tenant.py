from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eka.db.models import Tenant


async def get_tenant_by_slug(db: AsyncSession, slug: str) -> Tenant | None:
    return await db.scalar(select(Tenant).where(Tenant.slug == slug))
