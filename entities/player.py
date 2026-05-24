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
    username: str = ""        # linked account username (empty = guest)
    hp: int = 100
    max_hp: int = 100
    inventory: list[str] = field(default_factory=list)
    worn: dict = field(default_factory=dict)     # slot → item_id
    flags: dict = field(default_factory=dict)
    session_id: Optional[str] = None
    history: list[HistoryEntry] = field(default_factory=list)

    def worn_effects(self, world_items: dict) -> set[str]:
        """Compute the set of active effects from all currently worn items."""
        effects: set[str] = set()
        for item_id in self.worn.values():
            item = world_items.get(item_id)
            if item:
                effects.update(item.properties.get("effects", []))
        # Also fold in script-set flags (e.g. flags["muted"] = True)
        for key in ("muted", "restrained", "blindfolded", "no_move"):
            if self.flags.get(key):
                effects.add(key)
        return effects

    def has_effect(self, effect: str, world_items: dict) -> bool:
        return effect in self.worn_effects(world_items)

    def to_state(self) -> dict:
        """Serialisable snapshot for account persistence."""
        return {
            "room_id": self.room_id,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "inventory": list(self.inventory),
            "worn": dict(self.worn),
            "flags": dict(self.flags),
        }

    @staticmethod
    def from_state(state: dict, player: "Player") -> "Player":
        """Apply a saved state dict onto an existing player object."""
        player.room_id = state.get("room_id", player.room_id)
        player.hp = state.get("hp", player.hp)
        player.max_hp = state.get("max_hp", player.max_hp)
        player.inventory = list(state.get("inventory", player.inventory))
        player.worn = dict(state.get("worn", player.worn))
        player.flags = dict(state.get("flags", player.flags))
        return player

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
