import base64
import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def _derive_key(raw_key: str) -> bytes:
    """
    Derive a 32-byte key for AES-GCM from an arbitrary secret string.

    Using HKDF keeps the key stable across restarts while allowing flexible input
    (env var or fallback secret).
    """
    raw_bytes = raw_key.encode("utf-8")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"kontext-agent-aesgcm",
        info=b"transcript-encryption",
    )
    return hkdf.derive(raw_bytes)


def get_aesgcm(key_material: str) -> AESGCM:
    """Return an AESGCM instance derived from the provided key material."""
    return AESGCM(_derive_key(key_material))


def encrypt_text(plaintext: Optional[str], key_material: str) -> str:
    """
    Encrypt text with AES-GCM, returning base64(nonce + ciphertext+tag).

    Args:
        plaintext: Text to encrypt. None or empty returns empty string.
        key_material: Raw secret string from settings.
    """
    if not plaintext:
        return ""
    aesgcm = get_aesgcm(key_material)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("utf-8")


def decrypt_text(token: Optional[str], key_material: str) -> str:
    """
    Decrypt base64(nonce + ciphertext+tag) produced by encrypt_text.
    Returns empty string for None/empty input.
    Falls back to returning the raw value for legacy unencrypted records.
    """
    if not token:
        return ""
    try:
        data = base64.b64decode(token)
    except Exception:
        # Not valid base64 — legacy plain-text record, return as-is
        return token
    if len(data) <= 12:
        # Too short to be a valid nonce+ciphertext — treat as plain text
        return token
    nonce, ct = data[:12], data[12:]
    aesgcm = get_aesgcm(key_material)
    try:
        pt = aesgcm.decrypt(nonce, ct, None)
        return pt.decode("utf-8")
    except Exception:
        # Wrong key or corrupt — return raw value rather than silently dropping it
        return token
