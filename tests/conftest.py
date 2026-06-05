import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from eka.db.models import Base, Tenant, User, UserRole
from eka.deps import get_db_session
from eka.main import app
from eka.services.auth import get_password_hash
from eka.services.token import create_token_pair

# ──────────────────────────────────────────────
# Тестовая БД
# ──────────────────────────────────────────────


@pytest.fixture(scope="session")
def postgres_container():
    # Используем актуальную для проекта 18-ю версию
    with PostgresContainer("postgres:18") as postgres:
        yield postgres


@pytest_asyncio.fixture(scope="session")
async def test_engine(postgres_container):
    url = postgres_container.get_connection_url()

    # Универсальная замена любого синхронного драйвера на asyncpg
    if "://" in url:
        _, address = url.split("://", 1)
        async_url = f"postgresql+asyncpg://{address}"
    else:
        async_url = url.replace("postgresql://", "postgresql+asyncpg://")

    engine = create_async_engine(async_url, echo=False, poolclass=NullPool)
    yield engine

    await engine.dispose()


@pytest.fixture(scope="session")
def db_session_maker(test_engine):
    """Создает фабрику сессий один раз на всю сессию тестов."""
    return async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables(test_engine):
    """Создаёт все таблицы один раз перед стартом тестов."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest_asyncio.fixture(scope="function")
async def db(test_engine):
    """
    Изоляция тестов через транзакцию.
    Передаем db_session_maker как аргумент, pytest сам подставит фабрику.
    """
    async with test_engine.connect() as connection:
        transaction = await connection.begin()

        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")

        yield session

        await session.close()
        await transaction.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(db: AsyncSession):
    """
    Тестовый клиент, который заставляет FastAPI использовать
    нашу тестовую сессию с настроенным откатом (rollback).
    """
    # Подменяем зависимость базы данных
    app.dependency_overrides[get_db_session] = lambda: db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    # Очищаем переопределение после теста
    app.dependency_overrides.clear()


# ──────────────────────────────────────────────
# Фабрики тестовых объектов
# ──────────────────────────────────────────────


async def create_tenant(db: AsyncSession, name: str = "Test Corp") -> Tenant:
    from slugify import slugify

    tenant = Tenant(name=name, slug=slugify(name))
    db.add(tenant)
    await db.flush()
    return tenant


async def create_user(
    db: AsyncSession,
    tenant: Tenant,
    email: str = "user@test.com",
    password: str = "password123",
    role: UserRole = UserRole.user,
) -> User:
    user = User(
        email=email,
        hashed_password=get_password_hash(password),
        tenant_id=tenant.id,
        role=role,
    )
    db.add(user)
    await db.flush()
    return user


def auth_headers(user: User) -> dict:
    """Возвращает заголовок Authorization для пользователя."""
    tokens = create_token_pair(user_id=user.id)
    return {"Authorization": f"Bearer {tokens.access_token}"}


# ──────────────────────────────────────────────
# Готовые фикстуры для часто используемых объектов
# ──────────────────────────────────────────────


@pytest_asyncio.fixture(scope="function")
async def tenant(db):
    return await create_tenant(db)


@pytest_asyncio.fixture
async def regular_user(db, tenant):
    return await create_user(db, tenant, email="user@test.com", role=UserRole.user)


@pytest_asyncio.fixture
async def admin_user(db, tenant):
    return await create_user(db, tenant, email="admin@test.com", role=UserRole.admin)


@pytest.fixture
def user_headers(regular_user):
    return auth_headers(regular_user)


@pytest.fixture
def admin_headers(admin_user):
    return auth_headers(admin_user)
