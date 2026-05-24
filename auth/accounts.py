"""Player account management with PBKDF2-HMAC password hashing."""
from __future__ import annotations
import hashlib
import json
import logging
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_DATA_ROOT = Path(__file__).parent.parent / "data" / "players"


@dataclass
class Account:
    username: str
    password_hash: str   # "salt$hash" hex strings
    created_at: str = ""
    last_login: str = ""
    # role: "player" | "world_admin" | "admin"
    role: str = "player"
    # world IDs a world_admin is allowed to manage
    managed_worlds: list = field(default_factory=list)
    # player profile
    email: str = ""
    sex: str = ""           # free text, player self-describes
    real_age: str = ""      # free text, e.g. "25" or "adult"
    description: str = ""   # physical / bio description the player writes
    # saved world state: keyed by world_id
    world_states: dict = field(default_factory=dict)
    # per-world context notes: keyed by world_id, arbitrary text
    world_context: dict = field(default_factory=dict)


class AccountManager:
    def __init__(self):
        _DATA_ROOT.mkdir(parents=True, exist_ok=True)

    # ── public API ────────────────────────────────────────────────────────────

    def register(self, username: str, password: str) -> tuple[bool, str]:
        """Return (ok, error_message). error_message is empty on success."""
        username = username.strip().lower()
        if not username or len(username) < 2:
            return False, "Username must be at least 2 characters"
        if len(username) > 32:
            return False, "Username must be 32 characters or fewer"
        if not username.replace("_", "").replace("-", "").isalnum():
            return False, "Username may only contain letters, numbers, - and _"
        if not password or len(password) < 4:
            return False, "Password must be at least 4 characters"
        if self._account_path(username).exists():
            return False, "Username already taken"

        acc = Account(
            username=username,
            password_hash=_hash_password(password),
            created_at=_now(),
            last_login=_now(),
        )
        self._save_account(acc)
        log.info("Account registered: %s", username)
        return True, ""

    def login(self, username: str, password: str) -> tuple[bool, str]:
        """Return (ok, error_message)."""
        username = username.strip().lower()
        acc = self._load_account(username)
        if acc is None:
            return False, "Unknown username"
        if not _verify_password(password, acc.password_hash):
            return False, "Wrong password"
        acc.last_login = _now()
        self._save_account(acc)
        log.info("Account login: %s", username)
        return True, ""

    def get(self, username: str) -> Optional[Account]:
        return self._load_account(username.strip().lower())

    def list_accounts(self) -> list[dict]:
        """Return public summary of all accounts."""
        result = []
        if not _DATA_ROOT.exists():
            return result
        for acc_dir in _DATA_ROOT.iterdir():
            if not acc_dir.is_dir():
                continue
            acc = self._load_account(acc_dir.name)
            if acc:
                result.append({
                    "username":       acc.username,
                    "role":           acc.role,
                    "managed_worlds": acc.managed_worlds,
                    "created_at":     acc.created_at,
                    "last_login":     acc.last_login,
                })
        return result

    def set_role(self, username: str, role: str,
                 managed_worlds: list | None = None) -> tuple[bool, str]:
        if role not in ("player", "world_admin", "admin"):
            return False, "Invalid role"
        acc = self._load_account(username.strip().lower())
        if acc is None:
            return False, "Account not found"
        acc.role = role
        if managed_worlds is not None:
            acc.managed_worlds = list(managed_worlds)
        self._save_account(acc)
        return True, ""

    def update_profile(self, username: str, **fields) -> tuple[bool, str]:
        """Update profile fields (email, sex, real_age, description)."""
        acc = self._load_account(username.strip().lower())
        if acc is None:
            return False, "Account not found"
        allowed = {"email", "sex", "real_age", "description"}
        for k, v in fields.items():
            if k in allowed:
                setattr(acc, k, str(v)[:256])
        self._save_account(acc)
        return True, ""

    def change_password(self, username: str, old_pw: str, new_pw: str) -> tuple[bool, str]:
        username = username.strip().lower()
        acc = self._load_account(username)
        if acc is None:
            return False, "Account not found"
        if not _verify_password(old_pw, acc.password_hash):
            return False, "Current password is wrong"
        if not new_pw or len(new_pw) < 4:
            return False, "New password must be at least 4 characters"
        acc.password_hash = _hash_password(new_pw)
        self._save_account(acc)
        return True, ""

    def set_world_context(self, username: str, world_id: str, context: str):
        acc = self._load_account(username.strip().lower())
        if acc is None:
            return
        acc.world_context[world_id] = context
        self._save_account(acc)

    def get_world_context(self, username: str, world_id: str) -> str:
        acc = self._load_account(username.strip().lower())
        if acc is None:
            return ""
        return acc.world_context.get(world_id, "")

    def save_world_state(self, username: str, world_id: str, state: dict):
        acc = self._load_account(username)
        if acc is None:
            return
        acc.world_states[world_id] = state
        self._save_account(acc)

    def load_world_state(self, username: str, world_id: str) -> Optional[dict]:
        acc = self._load_account(username)
        if acc is None:
            return None
        return acc.world_states.get(world_id)

    # ── internal ──────────────────────────────────────────────────────────────

    def _account_path(self, username: str) -> Path:
        return _DATA_ROOT / username / "account.json"

    def _load_account(self, username: str) -> Optional[Account]:
        path = self._account_path(username)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Account(**data)
        except Exception:
            log.exception("Failed to load account: %s", username)
            return None

    def _save_account(self, acc: Account):
        path = self._account_path(acc.username)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(acc.__dict__, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# ── password hashing (PBKDF2-HMAC-SHA256, stdlib only) ────────────────────────

def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return f"{salt}${h.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
    except ValueError:
        return False
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return secrets.compare_digest(h.hex(), expected)


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
