"""Per-player, per-world story log.

Appends JSONL entries to data/players/<username>/worlds/<world_id>/story.jsonl.
Used to produce a narrative record of the player's time in a world.

Entry types:
  enter_room  — player moved into a room (name, description, exits, npcs, items)
  player_say  — player typed a command/speech
  gm_reply    — GM/Ollama response text
  npc_say     — NPC dialogue seen
  item_pick   — player picked up an item
  item_drop   — player dropped an item
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_DATA_ROOT = Path(__file__).parent.parent / "data" / "players"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class StoryLog:
    def __init__(self, username: str, world_id: str):
        self._path = _DATA_ROOT / username / "worlds" / world_id / "story.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry_type: str, **data: Any):
        entry = {"ts": _now(), "type": entry_type, **data}
        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            log.exception("StoryLog write failed: %s", self._path)

    def tail(self, n: int = 200) -> list[dict]:
        """Return the last n entries from the log."""
        if not self._path.exists():
            return []
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
            return [json.loads(l) for l in lines[-n:] if l.strip()]
        except Exception:
            log.exception("StoryLog read failed: %s", self._path)
            return []

    def all(self) -> list[dict]:
        return self.tail(n=10_000)
