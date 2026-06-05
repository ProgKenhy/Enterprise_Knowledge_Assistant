from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from eka.db.models import User
from eka.deps import get_db_session, get_user_by_token
from eka.schemas.user import UserRegister, UserResponse
from eka.services.user import register_user

users_router = APIRouter()


@users_router.post("/register", response_model=UserResponse, status_code=201)
async def register_user_endpoint(
    body: UserRegister, db: Annotated[AsyncSession, Depends(get_db_session)]
):
    new_user = await register_user(body, db)
    return UserResponse.model_validate(new_user)


@users_router.get("/me", response_model=UserResponse)
async def read_users_me_endpoint(
    current_user: Annotated[User, Depends(get_user_by_token)],
):
    return UserResponse.model_validate(current_user, from_attributes=True)
