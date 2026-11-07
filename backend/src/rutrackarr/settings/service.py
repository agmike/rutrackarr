"""Read/write settings; secrets are encrypted and never returned in plaintext by the API."""

import secrets as pysecrets
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from rutrackarr.crypto import SecretBox
from rutrackarr.db.models import SettingRow
from rutrackarr.settings.schema import API_KEY, FIELDS, FieldDef


class SettingsError(ValueError):
    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


class ApiKeyPinnedError(RuntimeError):
    pass


def _validate(key: str, field: FieldDef, raw: Any) -> str:
    if field.kind == "int":
        if isinstance(raw, bool) or not isinstance(raw, int | str):
            raise ValueError("must be a whole number")
        try:
            value = int(raw)
        except ValueError:
            raise ValueError("must be a whole number") from None
        if field.minimum is not None and value < field.minimum:
            raise ValueError(f"must be at least {field.minimum}")
        if field.maximum is not None and value > field.maximum:
            raise ValueError(f"must be at most {field.maximum}")
        return str(value)
    if not isinstance(raw, str):
        raise ValueError("must be text")
    value = raw.strip()
    if field.kind == "choice" and value not in field.choices:
        raise ValueError(f"must be one of: {', '.join(field.choices)}")
    if (field.kind == "url" or field.url) and value:
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("must be an http(s) URL")
    return value


class SettingsService:
    def __init__(self, sessions: sessionmaker, box: SecretBox, pinned_api_key: str | None) -> None:
        self._sessions = sessions
        self._box = box
        self._pinned_api_key = (pinned_api_key or "").strip() or None
        self._upgrade()

    def _upgrade(self) -> None:
        """Bring stored settings in line with the definitions: values that became secrets are
        encrypted, ones that stopped being secrets decrypted; a qui client-proxy URL saved as
        the qBittorrent URL (v0.10.1) becomes qui URL + token."""
        now = datetime.now(UTC)
        with self._sessions.begin() as s:
            rows = {r.key: r for r in s.scalars(select(SettingRow))}
            for row in rows.values():
                field = FIELDS.get(row.key)
                if field is None or not row.value:
                    continue
                if field.kind == "secret" and not row.is_secret:
                    row.value, row.is_secret = self._box.encrypt(row.value), True
                elif field.kind != "secret" and row.is_secret and row.key != API_KEY:
                    row.value, row.is_secret = self._box.decrypt(row.value) or "", False
            url = rows.get("qbittorrent.url")
            if url is not None and "/proxy/" in url.value and "qui.url" not in rows:
                base, _, token = url.value.partition("/proxy/")
                token = token.strip("/")
                values = {"qui.url": base, "qbittorrent.mode": "qui", "qbittorrent.url": ""}
                for key, value in values.items():
                    row = rows.get(key) or SettingRow(key=key, updated_at=now)
                    row.value, row.is_secret, row.updated_at = value, False, now
                    s.add(row)
                s.add(SettingRow(key="qui.token", value=self._box.encrypt(token), is_secret=True,
                                 updated_at=now))  # fmt: skip

    def qbittorrent_target(
        self, **pending: str | None
    ) -> tuple[str | None, str | None, str | None]:
        """(Web API base URL, username, password) of the download client's qBittorrent; no
        login (None, None) through qui's client proxy. `pending`: unsaved form values by setting
        key with "." replaced by "_" (qbittorrent_mode, qui_url, qui_token…)."""

        def val(key: str) -> str:
            v = pending.get(key.replace(".", "_"))
            return str(v if v not in (None, "") else (self.get(key) or "")).strip()

        if val("qbittorrent.mode") == "qui":
            base, token = val("qui.url").rstrip("/"), val("qui.token").strip("/")
            return (f"{base}/proxy/{token}" if base and token else None), None, None
        return (
            (val("qbittorrent.url") or None),
            val("qbittorrent.username"),
            val("qbittorrent.password"),
        )

    # --- reading ---------------------------------------------------------------
    def _rows(self) -> dict[str, SettingRow]:
        with self._sessions() as s:
            return {r.key: r for r in s.scalars(select(SettingRow))}

    def get(self, key: str) -> str | int | None:
        """Effective value for internal use (secrets decrypted)."""
        field = FIELDS[key]
        row = self._rows().get(key)
        if row is None:
            return field.default
        if row.is_secret:
            return self._box.decrypt(row.value)
        return int(row.value) if field.kind == "int" else row.value

    def public_view(self) -> dict[str, Any]:
        """What the UI may see: plain values, and only set/unset for secrets."""
        rows = self._rows()
        values: dict[str, Any] = {}
        secrets_set: dict[str, bool] = {}
        for key, field in FIELDS.items():
            row = rows.get(key)
            if field.kind == "secret":
                secrets_set[key] = row is not None and self._box.decrypt(row.value) is not None
            elif row is None:
                values[key] = field.default
            else:
                values[key] = int(row.value) if field.kind == "int" else row.value
        return {
            "values": values,
            "secrets": secrets_set,
            "api_key_pinned": self._pinned_api_key is not None,
        }

    # --- writing ---------------------------------------------------------------
    def update(self, changes: dict[str, Any]) -> None:
        """Apply changes. For secrets: non-empty text sets, empty text clears."""
        errors: dict[str, str] = {}
        clean: dict[str, str] = {}
        for key, raw in changes.items():
            field = FIELDS.get(key)
            if field is None:
                errors[key] = "unknown setting"
                continue
            try:
                clean[key] = _validate(key, field, raw)
            except ValueError as e:
                errors[key] = str(e)
        if errors:
            raise SettingsError(errors)
        now = datetime.now(UTC)
        with self._sessions.begin() as s:
            for key, value in clean.items():
                is_secret = FIELDS[key].kind == "secret"
                existing = s.get(SettingRow, key)
                if is_secret and value == "":
                    if existing is not None:
                        s.delete(existing)
                    continue
                stored = self._box.encrypt(value) if is_secret else value
                if existing is None:
                    s.add(SettingRow(key=key, value=stored, is_secret=is_secret, updated_at=now))
                else:
                    existing.value, existing.is_secret, existing.updated_at = stored, is_secret, now

    # --- Torznab API key -------------------------------------------------------
    def api_key(self) -> str:
        if self._pinned_api_key:
            return self._pinned_api_key
        with self._sessions.begin() as s:
            row = s.get(SettingRow, API_KEY)
            value = self._box.decrypt(row.value) if row else None
            if value:
                return value
            value = pysecrets.token_hex(16)
            stored = self._box.encrypt(value)
            if row is None:
                s.add(
                    SettingRow(
                        key=API_KEY, value=stored, is_secret=True, updated_at=datetime.now(UTC)
                    )
                )
            else:
                row.value, row.updated_at = stored, datetime.now(UTC)
            return value

    def regenerate_api_key(self) -> str:
        if self._pinned_api_key:
            raise ApiKeyPinnedError("the API key is set by RUTRACKARR_API_KEY")
        value = pysecrets.token_hex(16)
        with self._sessions.begin() as s:
            row = s.get(SettingRow, API_KEY)
            stored = self._box.encrypt(value)
            if row is None:
                s.add(
                    SettingRow(
                        key=API_KEY, value=stored, is_secret=True, updated_at=datetime.now(UTC)
                    )
                )
            else:
                row.value, row.updated_at = stored, datetime.now(UTC)
        return value
