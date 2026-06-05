# import redis.asyncio as redis
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from eka.deps import get_db_session

# from deps import get_redis_client

health_router = APIRouter(tags=["health"])


@health_router.get("", summary="Health check", response_model=dict)
async def health_check(
    db: AsyncSession = Depends(get_db_session),
    # redis_client: redis.Redis = Depends(get_redis_client)
):
    """
    Проверка здоровья приложения.
    Возвращает статус подключения к БД, Redis и общий статус.
    """
    health_data = {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "services": {},
    }

    # Проверка PostgreSQL
    try:
        await db.scalar(select(literal(1)))
        health_data["services"]["postgresql"] = {
            "status": "healthy",
            "message": "Connection successful",
        }
    except Exception as e:
        health_data["status"] = "unhealthy"
        health_data["services"]["postgresql"] = {
            "status": "unhealthy",
            "message": str(e),
        }

    # # Проверка Redis
    # try:
    # 	await redis_client.ping()
    # 	health_data["services"]["redis"] = {
    # 		"status": "healthy",
    # 		"message": "Connection successful"
    # 	}
    # except Exception as e:
    # 	health_data["status"] = "unhealthy"
    # 	health_data["services"]["redis"] = {
    # 		"status": "unhealthy",
    # 		"message": str(e)
    # 	}

    # Проверка приложения
    health_data["services"]["app"] = {
        "status": "healthy",
        "message": "Application is running",
    }

    return health_data
