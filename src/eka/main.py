import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from eka.api.v1.routers import api_router as v1_router
from eka.config import get_settings
from eka.db.pg import engine

sys.path.append(str(Path(__file__).resolve().parent))

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # [STARTUP] Здесь можно проверить коннект к БД или запустить логирование
    yield
    # [SHUTDOWN] Очищаем пул соединений при остановке приложения
    await engine.dispose()


app = FastAPI(lifespan=lifespan)


app.include_router(v1_router, prefix=settings.API_V1_PREFIX)
