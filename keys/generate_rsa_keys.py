from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Определяем корень проекта (на 2 уровня выше этого скрипта)
# keys/generate_rsa_keys.py -> keys/ -> корень проекта
BASE_DIR = Path(__file__).resolve().parent.parent
KEYS_DIR = BASE_DIR / "keys"

# Создаем директорию, если её нет
KEYS_DIR.mkdir(parents=True, exist_ok=True)

private_key_path = KEYS_DIR / "private.pem"
public_key_path = KEYS_DIR / "public.pem"

# Проверка: не перезаписываем существующие ключи случайно
if private_key_path.exists() or public_key_path.exists():
    print("⚠️  Ключи уже существуют!")
    print(f"   Приватный: {private_key_path}")
    print(f"   Публичный: {public_key_path}")
    print("   Удалите их вручную, если хотите перегенерировать.")
    raise SystemExit(1)

private_key = rsa.generate_private_key(
    public_exponent=65537, key_size=2048, backend=default_backend()
)
public_key = private_key.public_key()

with open(private_key_path, "wb") as f:
    f.write(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

with open(public_key_path, "wb") as f:
    f.write(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

print("✅ Ключи сгенерированы")
print(f"🔑 Приватный ключ: {private_key_path}")
print(f"🔒 Публичный ключ: {public_key_path}")
