"""A single isolated game world with its own map, entities, scripts, and loop."""
from __future__ import annotations
import uuid
import logging
from dataclasses import dataclass, field
from typing import Optional

from world.map import WorldMap
from entities.player import Player
from entities.npc import NPC
from entities.monster import Monster
from entities.item import Item
from network.sessions import SessionManager
from engine.loop import GameLoop
from gm.interpreter import GMInterpreter
from scripting.context import ScriptContext

log = logging.getLogger(__name__)


@dataclass
class WorldConfig:
    id: str
    name: str
    description: str = ""
    max_players: int = 50
    ollama_model: str = "llama3"
    # arbitrary world-level flags scripts can read/set
    flags: set = field(default_factory=set)


class WorldInstance:
    def __init__(self, config: WorldConfig):
        self.config = config
        self.map = WorldMap()
        self.players: dict[str, Player] = {}
        self.npcs: dict[str, NPC] = {}
        self.monsters: dict[str, Monster] = {}
        self.items: dict[str, Item] = {}
        self.sessions = SessionManager()
        self.gm = GMInterpreter(model=config.ollama_model)
        self.scripts = ScriptContext(world_id=config.id)
        self._loop = GameLoop(self._tick)

    @property
    def id(self) -> str:
        return self.config.id

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def player_count(self) -> int:
        return len(self.players)

    # --- player lifecycle ---

    def join(self, session_id: str, player_name: str) -> Player:
        player_id = str(uuid.uuid4())
        start_room = self.map.default_entry_room()
        player = Player(id=player_id, name=player_name, room_id=start_room)
        player.session_id = session_id
        self.players[player_id] = player
        room = self.map.get_room(start_room)
        if room:
            room.add_entity(player_id)
        self.sessions.bind_player(session_id, player_id)
        self._loop.set_player_count(len(self.players))
        log.info("[%s] Player joined: %s", self.id, player_name)
        return player

    def leave(self, session_id: str):
        player_id = self.sessions.player_for_session(session_id)
        if player_id and player_id in self.players:
            player = self.players.pop(player_id)
            room = self.map.get_room(player.room_id)
            if room:
                room.remove_entity(player_id)
            self._loop.set_player_count(len(self.players))
            log.info("[%s] Player left: %s", self.id, player.name)

    # --- room view helper ---

    async def send_room_view(self, session_id: str, player: Player):
        room = self.map.get_room(player.room_id)
        if room is None:
            return
        others = [
            self.players[eid].name
            for eid in room.entity_ids
            if eid in self.players and eid != player.id
        ]
        npcs_here = [
            self.npcs[eid].name
            for eid in room.entity_ids
            if eid in self.npcs
        ]
        monsters_here = [
            self.monsters[eid].name
            for eid in room.entity_ids
            if eid in self.monsters
        ]
        await self.sessions.send(session_id, {
            "type": "room",
            "name": room.name,
            "description": room.description,
            "exits": list(room.exits.keys()),
            "players": others,
            "npcs": npcs_here,
            "monsters": monsters_here,
        })

    # --- loop ---

    def start_loop(self):
        import asyncio
        asyncio.create_task(self._loop.start())

    async def _tick(self):
        await self.scripts.run_routines(self)

    # --- world flags (for scripts) ---

    def set_flag(self, flag: str):
        self.config.flags.add(flag)

    def has_flag(self, flag: str) -> bool:
        return flag in self.config.flags

    def clear_flag(self, flag: str):
        self.config.flags.discard(flag)

    # --- spawn helpers (called by scripts and GM) ---

    def spawn_monster(self, monster: Monster):
        self.monsters[monster.id] = monster
        room = self.map.get_room(monster.room_id)
        if room:
            room.add_entity(monster.id)

    def place_item(self, item: Item, room_id: str):
        item.room_id = room_id
        self.items[item.id] = item
        room = self.map.get_room(room_id)
        if room:
            room.add_entity(item.id)
