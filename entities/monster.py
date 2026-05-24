from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Monster:
    id: str
    name: str
    description: str
    room_id: str
    hp: int = 20
    max_hp: int = 20
    attack: int = 5
    defence: int = 2
    behaviour_script: str = "aggressive"
    loot_table: list[str] = field(default_factory=list)  # item ids
    properties: dict = field(default_factory=dict)
    gm_generated: bool = False

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def take_damage(self, amount: int):
        self.hp = max(0, self.hp - max(0, amount - self.defence))
