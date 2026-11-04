"""Encryption of secrets at rest (Fernet).

The key comes from RUTRACKARR_SECRET_KEY or, when unset, from `<data_dir>/secret.key`,
which is generated on first start (mode 0600). Losing the key makes stored secrets
unreadable; they then have to be re-entered on the settings page.
"""

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

KEY_FILE = "secret.key"


class SecretBox:
    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    @classmethod
    def from_settings(cls, secret_key: str | None, data_dir: Path) -> "SecretBox":
        if secret_key:
            return cls(secret_key.strip().encode())
        path = data_dir / KEY_FILE
        if not path.exists():
            data_dir.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(Fernet.generate_key())
        return cls(path.read_bytes().strip())

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, token: str) -> str | None:
        """Plaintext, or None when the token can't be decrypted (key changed)."""
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken:
            return None
