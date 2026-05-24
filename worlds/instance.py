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
from debug.player_log import PlayerDebugLogger, is_enabled as debug_enabled
from auth.accounts import AccountManager
from storage.backup import BackupManager

log = logging.getLogger(__name__)


@dataclass
class WorldConfig:
    id: str
    name: str
    description: str = ""
    max_players: int = 50
    ollama_model: str = "llama3"
    flags: set = field(default_factory=set)


_accounts = AccountManager()


class WorldInstance:
    def __init__(self, config: WorldConfig):
        self.config  = config
        self.map     = WorldMap()
        self.players:  dict[str, Player]  = {}
        self.npcs:     dict[str, NPC]     = {}
        self.monsters: dict[str, Monster] = {}
        self.items:    dict[str, Item]    = {}
        self.sessions = SessionManager()
        self.gm       = GMInterpreter(model=config.ollama_model)
        self.scripts  = ScriptContext(world_id=config.id)
        self._loop    = GameLoop(self._tick)
        self._debug_loggers: dict[str, PlayerDebugLogger] = {}

    # ── identity ──────────────────────────────────────────────────────────────

    @property
    def id(self) -> str:
        return self.config.id

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def player_count(self) -> int:
        return len(self.players)

    @property
    def rooms(self) -> dict:
        """Convenience access for scripts: world.rooms[room_id] or world.rooms.get(room_id)."""
        return self.map._rooms

    async def broadcast_to_room(self, room_id: str, text: str):
        """Send a message to every player currently in room_id."""
        for player in list(self.players.values()):
            if player.room_id == room_id and player.session_id:
                await self.sessions.send(player.session_id, {"type": "message", "text": text})

    # ── debug logger access ───────────────────────────────────────────────────

    def get_debug_logger(self, player_id: str) -> Optional[PlayerDebugLogger]:
        """Returns the debug logger for a player, or None if debug is off."""
        return self._debug_loggers.get(player_id)

    # ── player lifecycle ──────────────────────────────────────────────────────

    def join(self, session_id: str, player_name: str, username: str = "") -> Player:
        player_id  = str(uuid.uuid4())
        start_room = self.map.default_entry_room()
        player = Player(id=player_id, name=player_name, room_id=start_room,
                        username=username)
        player.session_id = session_id

        # restore saved state from account if available
        if username:
            saved = _accounts.load_world_state(username, self.id)
            if saved:
                from entities.player import Player as P
                P.from_state(saved, player)
                # ensure restored room actually exists
                if not self.map.get_room(player.room_id):
                    player.room_id = start_room

        self.players[player_id] = player
        room = self.map.get_room(player.room_id)
        if room:
            room.add_entity(player_id)
        self.sessions.bind_player(session_id, player_id)
        self._loop.set_player_count(len(self.players))

        if debug_enabled():
            dbg = PlayerDebugLogger(self.config.id, player_id, player_name)
            dbg.join(player.room_id)
            self._debug_loggers[player_id] = dbg

        player.add_history("event", f"Entered {self.name} at {room.name if room else player.room_id}")
        log.info("[%s] Player joined: %s (account: %s)", self.id, player_name, username or "guest")
        return player

    def leave(self, session_id: str):
        player_id = self.sessions.player_for_session(session_id)
        if player_id and player_id in self.players:
            player = self.players.pop(player_id)
            room = self.map.get_room(player.room_id)
            if room:
                room.remove_entity(player_id)
            self._loop.set_player_count(len(self.players))

            # persist state for logged-in accounts
            if player.username:
                _accounts.save_world_state(player.username, self.id, player.to_state())
                log.debug("[%s] Saved state for %s", self.id, player.username)

            dbg = self._debug_loggers.pop(player_id, None)
            if dbg:
                dbg.close()

            log.info("[%s] Player left: %s", self.id, player.name)

    # ── room view ─────────────────────────────────────────────────────────────

    async def send_room_view(self, session_id: str, player: Player):
        room = self.map.get_room(player.room_id)
        if room is None:
            return
        others   = [self.players[e].name   for e in room.entity_ids if e in self.players   and e != player.id]
        npcs     = [self.npcs[e].name      for e in room.entity_ids if e in self.npcs]
        monsters = [self.monsters[e].name  for e in room.entity_ids if e in self.monsters]
        await self.sessions.send(session_id, {
            "type": "room",
            "name": room.name,
            "description": room.description,
            "exits": list(room.exits.keys()),
            "players": others,
            "npcs": npcs,
            "monsters": monsters,
        })

    # ── loop ──────────────────────────────────────────────────────────────────

    def start_loop(self):
        import asyncio
        asyncio.create_task(self._loop.start())

    async def _tick(self):
        await self.scripts.run_routines(self)

    # ── world flags ───────────────────────────────────────────────────────────

    def set_flag(self, flag: str):   self.config.flags.add(flag)
    def has_flag(self, flag: str):   return flag in self.config.flags
    def clear_flag(self, flag: str): self.config.flags.discard(flag)

    # ── spawn helpers ─────────────────────────────────────────────────────────

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
