"""Game Master: routes player input through scripted rules first, then Ollama."""
from __future__ import annotations
import json
import logging
import httpx
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entities.player import Player
    from worlds.instance import WorldInstance

log = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"

_DIRECTIONS = {"north", "south", "east", "west", "up", "down", "n", "s", "e", "w", "u", "d"}
_DIR_MAP = {"n": "north", "s": "south", "e": "east", "w": "west", "u": "up", "d": "down"}
_REVERSE_DIR = {"north": "south", "south": "north", "east": "west", "west": "east"}


class GMInterpreter:
    def __init__(self, model: str = OLLAMA_MODEL):
        self._model = model

    async def handle(self, player: "Player", text: str, world: "WorldInstance") -> str:
        words = text.lower().split()
        if not words:
            return "Hmm?"

        verb = words[0]

        if verb in _DIRECTIONS or (verb == "go" and len(words) > 1 and words[1] in _DIRECTIONS):
            direction = _DIR_MAP.get(verb, verb) if verb != "go" else _DIR_MAP.get(words[1], words[1])
            return await self._move(player, direction, world)

        if verb in ("look", "l"):
            return await self._look(player, world)

        if verb in ("say", "shout", "yell") and len(words) > 1:
            message = " ".join(words[1:])
            await world.sessions.broadcast(
                {"type": "message", "text": f'{player.name} says: "{message}"'},
                exclude=player.session_id,
            )
            return f'You say: "{message}"'

        if verb in ("quit", "exit", "logout"):
            return "Use the browser close button to disconnect."

        return await self._llm_handle(player, text, world)

    async def _move(self, player: "Player", direction: str, world: "WorldInstance") -> str:
        room = world.map.move(player.room_id, direction)
        if room is None:
            return f"You can't go {direction} from here."
        old_room = world.map.get_room(player.room_id)
        if old_room:
            old_room.remove_entity(player.id)
        player.move_to(room.id)
        room.add_entity(player.id)
        # fire movement rules
        await world.scripts.fire_rule("player_enter", player=player, room=room, world=world)
        return f"You head {direction}."

    async def _look(self, player: "Player", world: "WorldInstance") -> str:
        room = world.map.get_room(player.room_id)
        if room is None:
            return "You are in a void."
        exits = ", ".join(room.exits.keys()) or "none"
        others = [
            world.players[eid].name
            for eid in room.entity_ids
            if eid in world.players and eid != player.id
        ]
        npcs = [
            world.npcs[eid].name
            for eid in room.entity_ids
            if eid in world.npcs
        ]
        monsters = [
            world.monsters[eid].name
            for eid in room.entity_ids
            if eid in world.monsters
        ]
        parts = [room.name, room.description, f"Exits: {exits}"]
        if others:
            parts.append("Also here: " + ", ".join(others))
        if npcs:
            parts.append("NPCs: " + ", ".join(npcs))
        if monsters:
            parts.append("Enemies: " + ", ".join(monsters))
        return "\n".join(parts)

    async def _llm_handle(self, player: "Player", text: str, world: "WorldInstance") -> str:
        room = world.map.get_room(player.room_id)
        room_ctx = f"{room.name}: {room.description}" if room else "unknown location"

        system_prompt = (
            f"You are the Game Master of '{world.name}'. "
            "Respond in 1-3 sentences. Stay in character. "
            "You may describe new things the player discovers. "
            "If you create a new room, item, or NPC, output a JSON block tagged "
            "```create``` so the game engine can persist it.\n"
            f"Player: {player.name} | Location: {room_ctx}"
        )

        payload = {
            "model": self._model,
            "prompt": f"{system_prompt}\n\nPlayer says: {text}",
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(OLLAMA_URL, json=payload)
                resp.raise_for_status()
                data = resp.json()
                response_text: str = data.get("response", "").strip()
        except Exception as exc:
            log.warning("Ollama request failed: %s", exc)
            response_text = "The air shimmers strangely. (GM unavailable)"

        await self._apply_creations(response_text, room.id if room else None, world)
        visible = response_text.split("```create")[0].strip()
        return visible or "Nothing seems to happen."

    async def _apply_creations(self, text: str, current_room_id: str | None, world: "WorldInstance"):
        import re
        blocks = re.findall(r"```create\s*(\{.*?\})\s*```", text, re.DOTALL)
        for block in blocks:
            try:
                obj = json.loads(block)
                kind = obj.get("type")
                if kind == "room":
                    await self._create_room(obj, current_room_id, world)
                elif kind == "item":
                    await self._create_item(obj, current_room_id, world)
                elif kind == "npc":
                    await self._create_npc(obj, current_room_id, world)
            except Exception:
                log.warning("Failed to apply GM creation block: %s", block)

    async def _create_room(self, obj: dict, from_room_id: str | None, world: "WorldInstance"):
        from world.room import Room
        import uuid
        room_id = obj.get("id") or str(uuid.uuid4())
        room = Room(
            id=room_id, name=obj.get("name", "Unknown Room"),
            description=obj.get("description", ""),
            zone_id=obj.get("zone_id", "default"),
            x=obj.get("x", 0), y=obj.get("y", 0),
            gm_generated=True,
        )
        world.map.add_room(room)
        if from_room_id and obj.get("direction"):
            origin = world.map.get_room(from_room_id)
            if origin:
                origin.add_exit(obj["direction"], room_id)
                rev = _REVERSE_DIR.get(obj["direction"])
                if rev:
                    room.add_exit(rev, from_room_id)
        log.info("[%s] GM created room: %s", world.id, room.name)

    async def _create_item(self, obj: dict, room_id: str | None, world: "WorldInstance"):
        from entities.item import Item
        import uuid
        item = Item(
            id=obj.get("id") or str(uuid.uuid4()),
            name=obj.get("name", "Unknown Item"),
            description=obj.get("description", ""),
            item_type=obj.get("item_type", "misc"),
            gm_generated=True,
            room_id=room_id,
        )
        world.items[item.id] = item
        if room_id:
            room = world.map.get_room(room_id)
            if room:
                room.add_entity(item.id)
        log.info("[%s] GM created item: %s", world.id, item.name)

    async def _create_npc(self, obj: dict, room_id: str | None, world: "WorldInstance"):
        from entities.npc import NPC
        import uuid
        npc = NPC(
            id=obj.get("id") or str(uuid.uuid4()),
            name=obj.get("name", "Stranger"),
            description=obj.get("description", ""),
            room_id=room_id or world.map.default_entry_room(),
            gm_generated=True,
        )
        world.npcs[npc.id] = npc
        room = world.map.get_room(npc.room_id)
        if room:
            room.add_entity(npc.id)
        log.info("[%s] GM created NPC: %s", world.id, npc.name)
