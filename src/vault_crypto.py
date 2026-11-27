"""Passphrase-based authenticated encryption (Scrypt + AES-256-GCM) for local Vault export/import."""

import base64
import json
import os
from typing import Any, Dict


ENVELOPE_MAGIC = "aps_encrypted_vault"
ENVELOPE_VERSION = 1


def is_encrypted_vault_payload(data: Any) -> bool:
    """Return True if a parsed JSON payload is an encrypted Sanitizer vault envelope."""
    return isinstance(data, dict) and data.get(ENVELOPE_MAGIC) == ENVELOPE_VERSION


def has_vault_crypto_support() -> bool:
    """Return True if the optional cryptography package is installed for AES-256-GCM vaults."""
    try:
        import cryptography.hazmat.primitives.ciphers.aead  # noqa: F401
        import cryptography.hazmat.primitives.kdf.scrypt  # noqa: F401
        return True
    except ImportError:
        return False


def _derive_key(passphrase: str, salt: bytes, n: int = 2**15, r: int = 8, p: int = 1) -> bytes:
    try:
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except ImportError as exc:
        raise ValueError("Encrypted vault requires the optional 'cryptography' package") from exc

    if not isinstance(passphrase, str) or len(passphrase) < 4:
        raise ValueError("Passphrase must be at least 4 characters")
    kdf = Scrypt(salt=salt, length=32, n=n, r=r, p=p)
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt_vault_payload(payload: Dict[str, Any], passphrase: str) -> Dict[str, Any]:
    """Encrypt a JSON-serializable vault dictionary into an authenticated AES-256-GCM envelope."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise ValueError("Encrypted vault requires the optional 'cryptography' package") from exc

    salt = os.urandom(16)
    nonce = os.urandom(12)
    n_cost, r_cost, p_cost = 2**15, 8, 1
    key = _derive_key(passphrase, salt, n=n_cost, r=r_cost, p=p_cost)
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    aad = f"{ENVELOPE_MAGIC}:v{ENVELOPE_VERSION}".encode("ascii")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    return {
        ENVELOPE_MAGIC: ENVELOPE_VERSION,
        "kdf": "scrypt",
        "kdf_params": {"n": n_cost, "r": r_cost, "p": p_cost},
        "cipher": "AES-256-GCM",
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }


def decrypt_vault_payload(envelope: Dict[str, Any], passphrase: str) -> Dict[str, Any]:
    """Decrypt and authenticate an AES-256-GCM vault envelope; raises ValueError on wrong passphrase or tampering."""
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise ValueError("Encrypted vault requires the optional 'cryptography' package") from exc

    if not is_encrypted_vault_payload(envelope):
        raise ValueError("Unsupported encrypted vault format")
    if envelope.get("kdf") != "scrypt" or envelope.get("cipher") != "AES-256-GCM":
        raise ValueError("Unsupported encrypted vault algorithm")
    params = envelope.get("kdf_params")
    if not isinstance(params, dict):
        raise ValueError("Invalid encrypted vault KDF parameters")
    n_cost = int(params.get("n", 0))
    r_cost = int(params.get("r", 0))
    p_cost = int(params.get("p", 0))
    # Cap KDF cost parameters against DoS from crafted files.
    if n_cost < 2**12 or n_cost > 2**18 or (n_cost & (n_cost - 1)) != 0 or not (1 <= r_cost <= 16) or not (1 <= p_cost <= 4):
        raise ValueError("Invalid encrypted vault KDF parameters")
    try:
        salt = base64.b64decode(str(envelope.get("salt", "")), validate=True)
        nonce = base64.b64decode(str(envelope.get("nonce", "")), validate=True)
        ciphertext = base64.b64decode(str(envelope.get("ciphertext", "")), validate=True)
    except Exception as exc:
        raise ValueError("Malformed encrypted vault encoding") from exc
    if len(salt) != 16 or len(nonce) != 12 or len(ciphertext) < 16:
        raise ValueError("Malformed encrypted vault parameters")

    key = _derive_key(passphrase, salt, n=n_cost, r=r_cost, p=p_cost)
    aad = f"{ENVELOPE_MAGIC}:v{ENVELOPE_VERSION}".encode("ascii")
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise ValueError("Wrong passphrase or tampered encrypted vault") from exc
    decoded = json.loads(plaintext.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("Decrypted vault payload must be a JSON object")
    return decoded
