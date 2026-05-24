"""Single shared game state instance, imported by routes and the engine loop."""
from __future__ import annotations
import uuid
import logging
from typing import TYPE_CHECKING

from network.sessions import SessionManager
from world.map import WorldMap
from entities.player import Player
from gm.interpreter import GMInterpreter
from engine.loop import GameLoop

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


class GameState:
    def __init__(self):
        self.sessions = SessionManager()
        self.world = WorldMap()
        self.players: dict[str, Player] = {}
        self.gm = GMInterpreter()
        self._loop = GameLoop(self._tick)

    def start_loop(self):
        import asyncio
        asyncio.create_task(self._loop.start())

    def join(self, session_id: str, name: str) -> Player:
        player_id = str(uuid.uuid4())
        start_room = "town_square"
        player = Player(id=player_id, name=name, room_id=start_room)
        player.session_id = session_id
        self.players[player_id] = player
        room = self.world.get_room(start_room)
        if room:
            room.add_entity(player_id)
        self.sessions.bind_player(session_id, player_id)
        self._loop.set_player_count(len(self.players))
        log.info("Player joined: %s (%s)", name, player_id)
        return player

    def leave(self, session_id: str):
        player_id = self.sessions.player_for_session(session_id)
        if player_id and player_id in self.players:
            player = self.players.pop(player_id)
            room = self.world.get_room(player.room_id)
            if room:
                room.remove_entity(player_id)
            self._loop.set_player_count(len(self.players))
            log.info("Player left: %s", player.name)

    async def send_room_view(self, session_id: str, player: Player):
        room = self.world.get_room(player.room_id)
        if room is None:
            return
        others = [
            self.players[eid].name
            for eid in room.entity_ids
            if eid in self.players and eid != player.id
        ]
        await self.sessions.send(session_id, {
            "type": "room",
            "name": room.name,
            "description": room.description,
            "exits": list(room.exits.keys()),
            "players": others,
        })

    async def _tick(self):
        # placeholder — NPC movement, events, etc. added here later
        pass


game_state = GameState()
