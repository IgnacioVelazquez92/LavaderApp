import base64
import hashlib
from cryptography.fernet import Fernet
from django.conf import settings


def _derived_key_from_secret() -> bytes:
    """
    Deriva una key de 32 bytes desde SECRET_KEY (SHA256 + base64 urlsafe).
    Se mantiene estable mientras SECRET_KEY no cambie.
    """
    h = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(h)


def _fernet() -> Fernet:
    return Fernet(_derived_key_from_secret())


def encrypt_bytes(plain: bytes) -> bytes:
    """Encripta bytes en un token seguro (Fernet)."""
    return _fernet().encrypt(plain)


def decrypt_bytes(token: bytes) -> bytes:
    """Desencripta un token seguro (Fernet) a bytes planos."""
    return _fernet().decrypt(token)
