import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from app.config import settings


SALT_BYTES = 32


def _server_fernet() -> Fernet:
    return Fernet(settings.ENCRYPTION_KEY.encode())


def _password_fernet(password: str, salt: bytes) -> Fernet:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return Fernet(key)


def encrypt(content: str, password: str | None, slug: str) -> tuple[str, str | None]:
    data: bytes = content.encode("utf-8")
    data = _server_fernet().encrypt(data)
    password_salt: str | None = None

    if password:
        salt = os.urandom(SALT_BYTES)
        password_salt = base64.urlsafe_b64encode(salt).decode()
        data = _password_fernet(password, salt).encrypt(data)

    return data.decode("utf-8"), password_salt


def decrypt(encrypted: str, password: str | None, slug: str, password_salt: str | None = None) -> str:
    try:
        data: bytes = encrypted.encode("utf-8")
        if password:
            if not password_salt:
                raise ValueError("WRONG_PASSWORD")
            salt = base64.urlsafe_b64decode(password_salt)
            data = _password_fernet(password, salt).decrypt(data)
        data = _server_fernet().decrypt(data)
        return data.decode("utf-8")
    except InvalidToken:
        raise ValueError("WRONG_PASSWORD")
