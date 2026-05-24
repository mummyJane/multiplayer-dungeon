from __future__ import annotations
from typing import Optional
from .room import Room
from .zone import Zone, ZoneType


class WorldMap:
    def __init__(self):
        self._rooms: dict[str, Room] = {}
        self._zones: dict[str, Zone] = {}

    # --- rooms ---

    def add_room(self, room: Room) -> Room:
        self._rooms[room.id] = room
        return room

    def get_room(self, room_id: str) -> Optional[Room]:
        return self._rooms.get(room_id)

    def rooms_in_zone(self, zone_id: str) -> list[Room]:
        return [r for r in self._rooms.values() if r.zone_id == zone_id]

    # --- zones ---

    def add_zone(self, zone: Zone) -> Zone:
        self._zones[zone.id] = zone
        return zone

    def get_zone(self, zone_id: str) -> Optional[Zone]:
        return self._zones.get(zone_id)

    # --- navigation ---

    def move(self, from_room_id: str, direction: str) -> Optional[Room]:
        room = self.get_room(from_room_id)
        if room is None:
            return None
        target_id = room.exits.get(direction.lower())
        if target_id is None:
            return None
        return self.get_room(target_id)

    # --- serialisation (for GM to persist new content) ---

    def to_dict(self) -> dict:
        return {
            "rooms": {k: vars(v) for k, v in self._rooms.items()},
            "zones": {k: vars(v) for k, v in self._zones.items()},
        }

    def seed_starter_world(self):
        """Build a minimal world to start with."""
        town = Zone(id="town", name="Thornwall", zone_type=ZoneType.OUTDOOR)
        self.add_zone(town)

        square = Room(
            id="town_square",
            name="Town Square",
            description="The dusty centre of Thornwall. A notice board creaks in the wind.",
            zone_id="town",
            x=0, y=0,
        )
        tavern_entry = Room(
            id="tavern_door",
            name="The Rusted Flagon — entrance",
            description="A low door leads into a smoky tavern. You can smell ale and old wood.",
            zone_id="town",
            x=1, y=0,
        )
        north_gate = Room(
            id="north_gate",
            name="North Gate",
            description="The town gate. Beyond lies the dark forest road.",
            zone_id="town",
            x=0, y=1,
        )

        square.add_exit("east", "tavern_door")
        square.add_exit("north", "north_gate")
        tavern_entry.add_exit("west", "town_square")
        north_gate.add_exit("south", "town_square")

        for room in (square, tavern_entry, north_gate):
            self.add_room(room)
            town.add_room(room.id)
