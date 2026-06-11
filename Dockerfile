# ──────────────────────────────────────────────
# Stage 1: Builder — устанавливаем зависимости
# ──────────────────────────────────────────────
# 1. Базовый образ
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "poetry>=2.0.0"

WORKDIR /build

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false \
    && poetry install --without dev --no-root --sync

# 5. И ТОЛЬКО ТЕПЕРЬ копируем остальной код
COPY . .

# ──────────────────────────────────────────────
# Stage 2: Runtime — финальный образ
# ──────────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 appuser

WORKDIR /app

COPY --from=builder /usr/local /usr/local

# Копируем код и сразу назначаем владельца через --chown
COPY --chown=appuser:appuser src/ src/
COPY --chown=appuser:appuser alembic/ alembic/
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

RUN mkdir -p uploads && chown appuser:appuser uploads

# Создаем папку для кэша моделей и отдаем права appuser
RUN mkdir -p /app/.cache/fastembed && chown -R appuser:appuser /app/.cache
# Указываем fastembed использовать эту папку
ENV FASTEMBED_CACHE_DIR="/app/.cache/fastembed"

USER appuser

ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "eka.main:app", "--host", "0.0.0.0", "--port", "8000"]