from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from eka.db.models import User
from eka.repositories.user import get_user_by_login

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


# ======== Пароли ========
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Хэширование пароля"""
    return pwd_context.hash(password)


# ======== Аутентификация ========
async def login_user(db: AsyncSession, login: str, password: str) -> User | None:
    """Аутентификация пользователя по username/email и password"""
    user = await get_user_by_login(login=login, db=db)
    if not user or not verify_password(password, str(user.hashed_password)):
        return None

    return user
