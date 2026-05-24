from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Item:
    id: str
    name: str
    description: str
    item_type: str = "misc"       # weapon, armour, consumable, misc
    weight: float = 0.0
    value: int = 0
    properties: dict = field(default_factory=dict)
    gm_generated: bool = False
    owner_id: Optional[str] = None
    room_id: Optional[str] = None
