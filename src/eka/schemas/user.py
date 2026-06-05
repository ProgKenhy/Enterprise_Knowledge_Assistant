from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from eka.db.models import UserRole


class UserCreate(BaseModel):
    email: EmailStr = Field(description="Почта пользователя")
    hashed_password: str
    tenant_id: UUID
    role: UserRole


class UserRegister(BaseModel):
    email: EmailStr = Field(description="Почта пользователя")
    password: str
    company_name: str


class UserResponse(BaseModel):
    id: UUID = Field(description="ID пользователя")
    email: EmailStr
    role: UserRole

    model_config = ConfigDict(from_attributes=True)
