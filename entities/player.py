from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

MAX_HISTORY = 100      # total entries kept on the player
HISTORY_FOR_LLM = 20  # how many recent entries the GM sees


@dataclass
class HistoryEntry:
    ts: str           # "HH:MM" — short, readable in LLM context
    kind: str         # move | input | gm | event | script
    text: str


@dataclass
class Player:
    id: str
    name: str
    room_id: str
    hp: int = 100
    max_hp: int = 100
    inventory: list[str] = field(default_factory=list)
    session_id: Optional[str] = None
    history: list[HistoryEntry] = field(default_factory=list)

    # ── history ───────────────────────────────────────────────────────────────

    def add_history(self, kind: str, text: str):
        ts = datetime.now().strftime("%H:%M")
        self.history.append(HistoryEntry(ts=ts, kind=kind, text=text))
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

    def history_for_llm(self) -> str:
        """Return the last HISTORY_FOR_LLM entries as a plain-text block."""
        recent = self.history[-HISTORY_FOR_LLM:]
        if not recent:
            return ""
        lines = [f"[{e.ts}] {e.text}" for e in recent]
        return "Recent history:\n" + "\n".join(lines)

    # ── vitals ────────────────────────────────────────────────────────────────

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def move_to(self, room_id: str):
        self.room_id = room_id

    def take_damage(self, amount: int):
        self.hp = max(0, self.hp - amount)

    def heal(self, amount: int):
        self.hp = min(self.max_hp, self.hp + amount)
