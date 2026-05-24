"""Per-player debug logger.

Enabled when the environment variable DEBUG_PLAYERS=1 (or DEBUG_PLAYERS=true).
One log file per player per world session:
    logs/<world_id>/<player_name>_<YYYYMMDD-HHMMSS>.log

Each line:
    [2026-05-24 13:01:02.345] [TYPE    ] message
    [2026-05-24 13:01:02.346] [DATA    ] {json}

Types used:
    JOIN        player connected
    LEAVE       player disconnected
    MOVE        room transition
    INPUT       raw player text
    SCRIPT      script triggered (which, event, why)
    LLM_SEND    prompt sent to LLM (model, truncated prompt)
    LLM_RECV    response from LLM (elapsed ms, text)
    LLM_ERR     LLM call failed
    STATE       snapshot of player + room state
    EVENT       game event (e.g. item found, combat start)
    ERROR       exception caught
"""
from __future__ import annotations
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

_LOGS_ROOT = Path(__file__).parent.parent / "logs"
_ENABLED: bool | None = None  # lazy-initialised


def is_enabled() -> bool:
    global _ENABLED
    if _ENABLED is None:
        val = os.environ.get("DEBUG_PLAYERS", "0").strip().lower()
        _ENABLED = val in ("1", "true", "yes")
    return _ENABLED


class PlayerDebugLogger:
    """Thread-safe line-at-a-time logger for one player session."""

    def __init__(self, world_id: str, player_id: str, player_name: str):
        self.world_id   = world_id
        self.player_id  = player_id
        self.player_name = player_name
        self._lock = threading.Lock()
        self._file = None

        if not is_enabled():
            return

        world_log_dir = _LOGS_ROOT / world_id
        world_log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in player_name)
        log_path = world_log_dir / f"{safe_name}_{ts}.log"
        self._file = open(log_path, "a", encoding="utf-8", buffering=1)  # line-buffered
        self._write_raw(f"=== DEBUG LOG: world={world_id}  player={player_name}  id={player_id} ===\n")

    # ── public API ────────────────────────────────────────────────────────────

    def log(self, log_type: str, message: str, data: dict | None = None):
        if not is_enabled() or self._file is None:
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        tag = log_type.upper().ljust(8)
        line = f"[{ts}] [{tag}] {message}\n"
        if data:
            line += f"[{ts}] [{'DATA'.ljust(8)}] {json.dumps(data, default=str)}\n"
        self._write_raw(line)

    def close(self):
        if self._file:
            self.log("LEAVE", "Session ended")
            with self._lock:
                self._file.close()
                self._file = None

    # ── shortcuts ─────────────────────────────────────────────────────────────

    def join(self, room_id: str):
        self.log("JOIN", f"Entered world in room '{room_id}'")

    def move(self, from_room: str, to_room: str, direction: str):
        self.log("MOVE", f"{from_room} → {to_room} (direction: {direction})")

    def player_input(self, text: str):
        self.log("INPUT", repr(text))

    def script_trigger(self, script_name: str, event: str, kwargs_summary: str):
        self.log("SCRIPT", f"{script_name}  event={event}  ctx={kwargs_summary}")

    def llm_send(self, model: str, prompt: str):
        # truncate prompt in log to keep files manageable
        preview = prompt[:600] + ("…" if len(prompt) > 600 else "")
        self.log("LLM_SEND", f"model={model}", {"prompt_chars": len(prompt), "preview": preview})

    def llm_recv(self, response: str, elapsed_ms: int):
        preview = response[:400] + ("…" if len(response) > 400 else "")
        self.log("LLM_RECV", f"elapsed={elapsed_ms}ms  chars={len(response)}", {"response": preview})

    def llm_error(self, error: str):
        self.log("LLM_ERR", error)

    def state_snapshot(self, player, room):
        self.log("STATE", "snapshot", {
            "room":     room.id if room else None,
            "hp":       getattr(player, "hp", "?"),
            "flags":    {k: v for k, v in player.__dict__.items()
                         if k.startswith("_") and not k.startswith("__")},
            "inventory": getattr(player, "inventory", []),
        })

    def event(self, description: str, data: dict | None = None):
        self.log("EVENT", description, data)

    def error(self, description: str):
        self.log("ERROR", description)

    # ── internal ──────────────────────────────────────────────────────────────

    def _write_raw(self, text: str):
        with self._lock:
            if self._file:
                self._file.write(text)
