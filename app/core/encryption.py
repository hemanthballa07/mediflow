import hashlib
import hmac
from cryptography.fernet import Fernet, InvalidToken
from app.core.config import get_settings


def _fernet() -> Fernet:
    return Fernet(get_settings().ENCRYPTION_KEY.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return ciphertext


def email_hash(email: str) -> str:
    key = get_settings().ENCRYPTION_KEY.encode()
    return hmac.new(key, email.lower().encode(), hashlib.sha256).hexdigest()
