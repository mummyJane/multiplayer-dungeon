from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ZoneType(str, Enum):
    OUTDOOR = "outdoor"
    INDOOR = "indoor"
    DUNGEON = "dungeon"
    BUILDING = "building"


@dataclass
class Zone:
    id: str
    name: str
    zone_type: ZoneType
    room_ids: list[str] = field(default_factory=list)
    entry_room_id: Optional[str] = None
    properties: dict = field(default_factory=dict)

    def add_room(self, room_id: str):
        if room_id not in self.room_ids:
            self.room_ids.append(room_id)
            if self.entry_room_id is None:
                self.entry_room_id = room_id
