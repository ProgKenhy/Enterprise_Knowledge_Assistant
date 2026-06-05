from fastapi import APIRouter

from eka.api.v1.endpoints.auth import auth_router
from eka.api.v1.endpoints.documents import documents_router
from eka.api.v1.endpoints.health import health_router
from eka.api.v1.endpoints.users import users_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(documents_router, prefix="/docs", tags=["docs"])
