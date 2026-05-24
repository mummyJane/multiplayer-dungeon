from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Player:
    id: str
    name: str
    room_id: str
    hp: int = 100
    max_hp: int = 100
    inventory: list[str] = field(default_factory=list)  # item ids
    # connection session id — set by network layer
    session_id: Optional[str] = None

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def move_to(self, room_id: str):
        self.room_id = room_id

    def take_damage(self, amount: int):
        self.hp = max(0, self.hp - amount)

    def heal(self, amount: int):
        self.hp = min(self.max_hp, self.hp + amount)
