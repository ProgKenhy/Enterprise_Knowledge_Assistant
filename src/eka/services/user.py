from fastapi import HTTPException, status
from slugify import slugify
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from eka.db.models import Tenant, User, UserRole
from eka.repositories.tenant import get_tenant_by_slug
from eka.repositories.user import create_user, get_user_by_email
from eka.schemas.user import UserCreate, UserRegister

from .auth import get_password_hash


async def register_user(body: UserRegister, db: AsyncSession) -> User:
    if await get_user_by_email(body.email, db):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    slug = slugify(body.company_name)

    existing_tenant = await get_tenant_by_slug(db, slug)
    if existing_tenant:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Company already registered. Ask your admin to invite you.",
        )

    tenant = Tenant(
        name=body.company_name,
        slug=slug,
    )
    db.add(tenant)
    await db.flush()

    user_create = UserCreate(
        email=body.email,
        hashed_password=get_password_hash(body.password),
        tenant_id=tenant.id,
        role=UserRole.admin,
    )

    try:
        user = await create_user(user_create, db)
        await db.commit()
        await db.refresh(user)
        return user
    except IntegrityError as err:
        await db.rollback()
        # IntegrityError может быть и из-за дублирующегося slug тенанта
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User or company already exists",
        ) from err
