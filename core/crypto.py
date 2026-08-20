"""Encryption for secrets stored in the database.

What this protects, precisely: the **database file**. jobs.db is the artefact
most likely to escape — copied somewhere for debugging, swept into a backup, or
picked up by a cloud sync client watching the folder. Encrypting the API key and
the mail password means a stray copy of the database is not a credential leak.

What it does not protect: anyone who can already read this directory, because
the key sits in `.secret_key` right beside it. Defending against that would need
a passphrase typed on every start, which is the wrong trade for a personal tool
that must run unattended at 9am.

So: worth doing, and worth describing accurately. Not a vault.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_KEY_FILE = Path(__file__).parent.parent / ".secret_key"
_PREFIX = "enc:v1:"          # tags ciphertext so plaintext rows migrate cleanly
_fernet: Fernet | None = None


def _load_or_create_key() -> bytes:
    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes().strip()

    key = Fernet.generate_key()
    _KEY_FILE.write_bytes(key)
    try:
        # Owner-only. A no-op on Windows in practice, but correct on POSIX and
        # harmless here.
        os.chmod(_KEY_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return key


def _cipher() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key())
    return _fernet


def encrypt(value: str) -> str:
    """Encrypt a secret for storage. Empty values stay empty — an unset secret
    should read as unset, not as ciphertext of an empty string."""
    if not value:
        return ""
    return _PREFIX + _cipher().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """Decrypt a stored secret.

    Untagged values are returned as-is: rows written before encryption existed,
    or a value someone edited into the database by hand, still work.
    """
    if not value:
        return ""
    if not value.startswith(_PREFIX):
        return value
    try:
        return _cipher().decrypt(value[len(_PREFIX):].encode()).decode()
    except (InvalidToken, ValueError):
        # Wrong or regenerated key. Treat as unset rather than crashing a
        # collection run — the UI will show the setting as not configured.
        return ""


def is_encrypted(value: str) -> bool:
    return bool(value) and value.startswith(_PREFIX)


def mask(value: str) -> str:
    """A hint the UI can show without revealing the secret."""
    if not value:
        return ""
    if len(value) <= 4:
        return "•" * len(value)
    return "•" * 4 + value[-4:]
