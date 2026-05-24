"""Game Master: scripted fast path → Ollama fallback with player history context."""
from __future__ import annotations
import json
import logging
import time
import httpx
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entities.player import Player
    from worlds.instance import WorldInstance
    from debug.player_log import PlayerDebugLogger

log = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"

_DIRECTIONS = {"north", "south", "east", "west", "up", "down", "n", "s", "e", "w", "u", "d"}
_DIR_MAP    = {"n": "north", "s": "south", "e": "east", "w": "west", "u": "up", "d": "down"}
_REVERSE    = {"north": "south", "south": "north", "east": "west", "west": "east"}

_NOISE_WORDS = {"the", "a", "an", "some", "my", "your"}


def _extract_target(words: list[str], start: int = 1) -> str:
    """Join words[start:] minus articles into an item-name search string."""
    return " ".join(w for w in words[start:] if w not in _NOISE_WORDS)


def _find_item(name: str, player, world) -> "Item | None":
    """Find an item by partial name match in inventory, worn items, or current room."""
    from entities.item import Item
    nl = name.lower()
    for iid in player.inventory:
        item = world.items.get(iid)
        if item and nl in item.name.lower():
            return item
    for iid in player.worn.values():
        item = world.items.get(iid)
        if item and nl in item.name.lower():
            return item
    room = world.map.get_room(player.room_id)
    if room:
        for eid in room.entity_ids:
            item = world.items.get(eid)
            if item and nl in item.name.lower():
                return item
    return None


def _find_in_room(name: str, player, world) -> "Item | None":
    """Find an item by partial name match in the current room only."""
    nl = name.lower()
    room = world.map.get_room(player.room_id)
    if not room:
        return None
    for eid in room.entity_ids:
        item = world.items.get(eid)
        if item and nl in item.name.lower():
            return item
    return None


class GMInterpreter:
    def __init__(self, model: str = OLLAMA_MODEL):
        self._model = model

    async def handle(self, player: "Player", text: str, world: "WorldInstance") -> str:
        dbg = world.get_debug_logger(player.id)
        if dbg:
            dbg.player_input(text)

        player.add_history("input", f'You: "{text}"')

        words = text.lower().split()
        if not words:
            return "Hmm?"

        verb = words[0]
        effects = player.worn_effects(world.items)

        # ── effect-gated commands ─────────────────────────────────────────────

        if verb in ("say", "shout", "yell", "whisper"):
            if "mute" in effects:
                return "You are gagged and cannot speak."
            if len(words) > 1:
                message = " ".join(words[1:])
                await world.sessions.broadcast(
                    {"type": "message", "text": f'{player.name} says: "{message}"'},
                    exclude=player.session_id,
                )
                response = f'You say: "{message}"'
            else:
                response = "Say what?"
            player.add_history("gm", response)
            return response

        if verb in _DIRECTIONS or (verb == "go" and len(words) > 1 and words[1] in _DIRECTIONS):
            direction = _DIR_MAP.get(verb, verb) if verb != "go" else _DIR_MAP.get(words[1], words[1])
            if "no_move" in effects:
                response = "You are restrained and cannot leave."
            else:
                response = await self._move(player, direction, world, dbg)

        elif verb in ("look", "l") and (len(words) == 1 or words[1] not in ("at", "in")):
            response = await self._look(player, world)

        elif (verb in ("look",) and len(words) > 1 and words[1] in ("at", "in")) \
                or verb in ("examine", "x", "inspect"):
            target = _extract_target(words, 2 if words[1:2] in [["at"], ["in"]] else 1)
            response = self._examine(target, player, world)

        # ── clothing: "take off X" must be checked before generic "take X" ────
        elif verb == "take" and words[1:2] == ["off"]:
            target = _extract_target(words, 2)
            response = self._remove_worn(target, player, world)

        elif verb in ("remove", "doff", "unequip"):
            target = _extract_target(words)
            response = self._remove_worn(target, player, world)

        elif verb in ("wear", "don", "equip"):
            target = _extract_target(words)
            response = self._wear(target, player, world)

        elif verb == "put" and words[1:2] == ["on"]:
            target = _extract_target(words, 2)
            response = self._wear(target, player, world)

        elif verb == "drop":
            target = _extract_target(words)
            response = self._drop(target, player, world)

        elif verb in ("inventory", "inv", "i"):
            response = self._inventory(player, world)

        elif verb in ("take", "get", "grab") or \
                (verb == "pick" and words[1:2] == ["up"]):
            start = 2 if (verb == "pick") else 1
            target = _extract_target(words, start)
            response = self._take(target, player, world)

        elif verb in ("quit", "exit", "logout"):
            response = "Use the browser close button to disconnect."

        else:
            response = await self._llm_handle(player, text, world, dbg)

        player.add_history("gm", response)
        return response

    # ── movement ──────────────────────────────────────────────────────────────

    async def _move(self, player: "Player", direction: str,
                    world: "WorldInstance", dbg) -> str:
        target = world.map.move(player.room_id, direction)
        if target is None:
            return f"You can't go {direction} from here."

        old_room_id = player.room_id
        old_room = world.map.get_room(old_room_id)
        if old_room:
            old_room.remove_entity(player.id)

        player.move_to(target.id)
        target.add_entity(player.id)

        if dbg:
            dbg.move(old_room_id, target.id, direction)
        player.add_history("move", f"Moved {direction} to {target.name}")

        await world.scripts.fire_rule(
            "player_enter", player=player, room=target, world=world
        )
        return f"You head {direction}."

    # ── look ──────────────────────────────────────────────────────────────────

    async def _look(self, player: "Player", world: "WorldInstance") -> str:
        room = world.map.get_room(player.room_id)
        if room is None:
            return "You are in a void."
        exits    = ", ".join(room.exits.keys()) or "none"
        others   = [world.players[e].name   for e in room.entity_ids if e in world.players   and e != player.id]
        npcs     = [world.npcs[e].name      for e in room.entity_ids if e in world.npcs]
        monsters = [world.monsters[e].name  for e in room.entity_ids if e in world.monsters]
        items_here = [world.items[e].name   for e in room.entity_ids if e in world.items]
        parts = [room.name, room.description, f"Exits: {exits}"]
        if others:     parts.append("Also here: " + ", ".join(others))
        if npcs:       parts.append("NPCs: "       + ", ".join(npcs))
        if monsters:   parts.append("Enemies: "    + ", ".join(monsters))
        if items_here: parts.append("Items: "      + ", ".join(items_here))
        return "\n".join(parts)

    # ── examine ───────────────────────────────────────────────────────────────

    def _examine(self, target: str, player: "Player", world: "WorldInstance") -> str:
        if not target:
            return "Examine what?"
        item = _find_item(target, player, world)
        if item:
            parts = [f"{item.name}: {item.description}"]
            if item.is_wearable and item.slot:
                parts.append(f"Worn on: {item.slot}")
            if item.item_effects:
                parts.append(f"Effects: {', '.join(item.item_effects)}")
            if item.is_fixture:
                parts.append("(This cannot be moved.)")
            if item.is_locked:
                parts.append("(Locked.)")
            return "\n".join(parts)
        # also check NPCs
        nl = target.lower()
        for npc in world.npcs.values():
            if nl in npc.name.lower():
                return f"{npc.name}: {npc.description}"
        return f"You don't see '{target}' here."

    # ── inventory ─────────────────────────────────────────────────────────────

    def _inventory(self, player: "Player", world: "WorldInstance") -> str:
        parts = []
        if player.inventory:
            names = [world.items[i].name for i in player.inventory if i in world.items]
            parts.append("Carrying: " + (", ".join(names) or "nothing"))
        else:
            parts.append("Carrying: nothing")
        if player.worn:
            worn_lines = []
            for slot, iid in sorted(player.worn.items()):
                item = world.items.get(iid)
                worn_lines.append(f"  {slot}: {item.name if item else iid}")
            parts.append("Wearing:\n" + "\n".join(worn_lines))
        effects = player.worn_effects(world.items)
        if effects:
            parts.append("Active effects: " + ", ".join(sorted(effects)))
        return "\n".join(parts)

    # ── take / drop ───────────────────────────────────────────────────────────

    def _take(self, target: str, player: "Player", world: "WorldInstance") -> str:
        if not target:
            return "Take what?"
        item = _find_in_room(target, player, world)
        if item is None:
            return f"You don't see '{target}' here."
        if item.is_fixture:
            return f"{item.name} is fixed in place and cannot be taken."
        room = world.map.get_room(player.room_id)
        if room:
            room.remove_entity(item.id)
        item.room_id = None
        player.inventory.append(item.id)
        return f"You pick up {item.name}."

    def _drop(self, target: str, player: "Player", world: "WorldInstance") -> str:
        if not target:
            return "Drop what?"
        nl = target.lower()
        for iid in list(player.inventory):
            item = world.items.get(iid)
            if item and nl in item.name.lower():
                player.inventory.remove(iid)
                item.room_id = player.room_id
                room = world.map.get_room(player.room_id)
                if room:
                    room.add_entity(iid)
                return f"You drop {item.name}."
        return f"You're not carrying '{target}'."

    # ── wear / remove ─────────────────────────────────────────────────────────

    def _wear(self, target: str, player: "Player", world: "WorldInstance") -> str:
        if not target:
            return "Wear what?"
        # search inventory first, then room
        nl = target.lower()
        item = None
        for iid in player.inventory:
            it = world.items.get(iid)
            if it and nl in it.name.lower():
                item = it
                break
        if item is None:
            item = _find_in_room(target, player, world)
        if item is None:
            return f"You don't see '{target}' here."
        if not item.is_wearable:
            return f"{item.name} is not something you can wear."
        slot = item.slot or "misc"
        if slot in player.worn:
            existing = world.items.get(player.worn[slot])
            ename = existing.name if existing else "something"
            return f"You are already wearing {ename} on your {slot}. Remove it first."
        # equip: remove from inventory / room, add to worn
        if item.id in player.inventory:
            player.inventory.remove(item.id)
        else:
            room = world.map.get_room(player.room_id)
            if room:
                room.remove_entity(item.id)
            item.room_id = None
        player.worn[slot] = item.id
        item.properties["worn_by"] = player.id
        effects = player.worn_effects(world.items)
        effect_note = ""
        if item.item_effects:
            effect_note = f" ({', '.join(item.item_effects)})"
        return f"You put on {item.name}.{effect_note}"

    def _remove_worn(self, target: str, player: "Player",
                     world: "WorldInstance") -> str:
        if not target:
            return "Remove what?"
        nl = target.lower()
        for slot, iid in list(player.worn.items()):
            item = world.items.get(iid)
            if item and nl in item.name.lower():
                if item.is_locked:
                    return f"{item.name} is locked on — you cannot remove it."
                del player.worn[slot]
                item.properties.pop("worn_by", None)
                player.inventory.append(iid)
                return f"You remove {item.name}."
        return f"You are not wearing '{target}'."

    # ── LLM fallback ──────────────────────────────────────────────────────────

    async def _llm_handle(self, player: "Player", text: str,
                          world: "WorldInstance", dbg) -> str:
        room = world.map.get_room(player.room_id)
        room_ctx = f"{room.name}: {room.description}" if room else "unknown location"

        history_block = player.history_for_llm()

        # Build worn / effects context
        worn_names = [world.items[i].name for i in player.worn.values() if i in world.items]
        effects = player.worn_effects(world.items)
        worn_str   = f"Wearing: {', '.join(worn_names)}\n" if worn_names else ""
        effect_str = f"Active effects: {', '.join(sorted(effects))}\n" if effects else ""

        system_prompt = (
            f"You are the Game Master of '{world.name}'. "
            "Respond in 1-3 sentences. Stay in character. "
            "You may describe new things the player discovers. "
            "To create a new item or NPC, output a JSON block tagged ```create``` "
            "(one object). Items may be wearable clothing. "
            "Item JSON format: {\"type\":\"item\",\"id\":\"slug\",\"name\":\"Name\","
            "\"description\":\"Desc\",\"item_type\":\"clothing|misc|fixture\","
            "\"properties\":{\"wearable\":true,\"slot\":\"mouth|top|bottom|nappy|"
            "outerwear|head|hands|restraint|misc\",\"effects\":[\"mute\"|\"no_move\"|"
            "\"blindfold\"],\"lockable\":true,\"fixture\":false}}\n"
            f"Player: {player.name}  HP: {player.hp}/{player.max_hp}\n"
            f"Location: {room_ctx}\n"
            f"{worn_str}{effect_str}"
        )
        if history_block:
            system_prompt += f"\n{history_block}\n"

        prompt = f"{system_prompt}\n\nPlayer says: {text}"

        if dbg:
            dbg.llm_send(self._model, prompt)
            dbg.state_snapshot(player, room)

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(OLLAMA_URL, json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                })
                resp.raise_for_status()
                response_text: str = resp.json().get("response", "").strip()
        except Exception as exc:
            err_msg = str(exc)
            log.warning("Ollama request failed: %s", err_msg)
            if dbg:
                dbg.llm_error(err_msg)
            return "The air shimmers strangely. (GM unavailable)"

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        if dbg:
            dbg.llm_recv(response_text, elapsed_ms)

        await self._apply_creations(response_text, room.id if room else None, world)
        visible = response_text.split("```create")[0].strip()
        return visible or "Nothing seems to happen."

    # ── GM world-creation ─────────────────────────────────────────────────────

    async def _apply_creations(self, text: str, current_room_id: str | None,
                               world: "WorldInstance"):
        import re
        for block in re.findall(r"```create\s*(\{.*?\})\s*```", text, re.DOTALL):
            try:
                obj = json.loads(block)
                kind = obj.get("type")
                if kind == "room":  await self._create_room(obj, current_room_id, world)
                elif kind == "item": await self._create_item(obj, current_room_id, world)
                elif kind == "npc":  await self._create_npc(obj, current_room_id, world)
            except Exception:
                log.warning("Failed to apply GM creation block: %s", block)

    async def _create_room(self, obj: dict, from_room_id: str | None,
                           world: "WorldInstance"):
        from world.room import Room
        import uuid
        room = Room(
            id=obj.get("id") or str(uuid.uuid4()),
            name=obj.get("name", "Unknown Room"),
            description=obj.get("description", ""),
            zone_id=obj.get("zone_id", "default"),
            x=obj.get("x", 0), y=obj.get("y", 0),
            creator="local_llm",
        )
        world.map.add_room(room)
        if from_room_id and obj.get("direction"):
            origin = world.map.get_room(from_room_id)
            if origin:
                origin.add_exit(obj["direction"], room.id)
                rev = _REVERSE.get(obj["direction"])
                if rev:
                    room.add_exit(rev, from_room_id)
        log.info("[%s] GM created room: %s", world.id, room.name)

    async def _create_item(self, obj: dict, room_id: str | None,
                           world: "WorldInstance"):
        from entities.item import Item
        import uuid
        item = Item(
            id=obj.get("id") or str(uuid.uuid4()),
            name=obj.get("name", "Unknown Item"),
            description=obj.get("description", ""),
            item_type=obj.get("item_type", "misc"),
            properties=obj.get("properties", {}),
            creator="local_llm", room_id=room_id,
        )
        world.items[item.id] = item
        if room_id:
            room = world.map.get_room(room_id)
            if room:
                room.add_entity(item.id)
        log.info("[%s] GM created item: %s", world.id, item.name)

    async def _create_npc(self, obj: dict, room_id: str | None,
                          world: "WorldInstance"):
        from entities.npc import NPC
        import uuid
        npc = NPC(
            id=obj.get("id") or str(uuid.uuid4()),
            name=obj.get("name", "Stranger"),
            description=obj.get("description", ""),
            room_id=room_id or world.map.default_entry_room(),
            creator="local_llm",
        )
        world.npcs[npc.id] = npc
        room = world.map.get_room(npc.room_id)
        if room:
            room.add_entity(npc.id)
        log.info("[%s] GM created NPC: %s", world.id, npc.name)
