from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Room:
    id: str
    name: str
    description: str
    zone_id: str
    x: int
    y: int
    z: int = 0     # floor level: negative=basement, 0=ground, positive=upper floors
    # cardinal + vertical exits: direction -> room_id
    # directions: north south east west up down in out
    exits: dict[str, str] = field(default_factory=dict)
    # ids of entities currently in this room
    entity_ids: list[str] = field(default_factory=list)
    # arbitrary script-defined properties
    properties: dict = field(default_factory=dict)
    # set True when the GM created this at runtime
    gm_generated: bool = False

    def add_exit(self, direction: str, target_room_id: str):
        self.exits[direction.lower()] = target_room_id

    def add_entity(self, entity_id: str):
        if entity_id not in self.entity_ids:
            self.entity_ids.append(entity_id)

    def remove_entity(self, entity_id: str):
        self.entity_ids = [e for e in self.entity_ids if e != entity_id]
