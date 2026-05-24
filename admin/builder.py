"""Claude API world builder.

Accepts either a short theme description or a full detailed spec document.
Returns a structured world dict which materialise_world() writes to disk.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path

import anthropic

log = logging.getLogger(__name__)

_DATA_ROOT = Path(__file__).parent.parent / "data" / "worlds"

_SYSTEM = """\
You are a game world designer for a real-time multiplayer text RPG engine.
You receive either:
  A) A short theme (1–3 sentences), or
  B) A detailed world specification document.

Return ONLY a valid JSON object — no markdown fences, no commentary.
For a detailed spec, extract ALL rooms and NPCs described; do not summarise or skip any.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REQUIRED JSON SHAPE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "config": {
    "id": "<lowercase-slug>",
    "name": "<display name>",
    "description": "<1-2 sentences>",
    "max_players": <int>,
    "ollama_model": "llama3"
  },
  "zones": [
    {
      "id": "<slug>",
      "name": "<name>",
      "zone_type": "outdoor|indoor|dungeon|building"
    }
  ],
  "rooms": [
    {
      "id": "<slug>",
      "name": "<display name>",
      "description": "<2-3 sentences, flavourful>",
      "zone_id": "<zone id>",
      "x": <int>,
      "y": <int>,
      "z": <int>,           // floor level: -2=deep basement, -1=basement, 0=ground, 1=first, 2=second, 3=loft
      "exits": {
        "north": "<room_id>",   // optional — only include exits that exist
        "up": "<room_id>",      // use "up"/"down" for stairs between floors
        "down": "<room_id>"
      },
      "properties": {         // optional — arbitrary metadata for scripts
        "floor": "basement",
        "room_type": "punishment_nursery",
        "capacity": 1
      },
      "entry": true           // mark exactly ONE room as the player entry point
    }
  ],
  "npcs": [
    {
      "id": "<slug>",
      "name": "<name>",
      "description": "<1 sentence>",
      "room_id": "<room_id>",
      "dialogue": ["<line>", "..."],
      "properties": {         // optional — scheduling and role metadata for scripts
        "role": "head_nanny",
        "shift": "day",       // day | night | swing
        "shift_start": "07:00",
        "shift_end": "19:00"
      }
    }
  ],
  "monsters": [
    {
      "id": "<slug>", "name": "<name>", "description": "<sentence>",
      "room_id": "<room_id>",
      "hp": <int>, "attack": <int>, "defence": <int>
    }
  ],
  "items": [
    {
      "id": "<slug>", "name": "<name>", "description": "<sentence>",
      "item_type": "clothing|consumable|misc|weapon|armour",
      "room_id": "<room_id or null>",
      "properties": {}
    }
  ],
  "rules_script":    "<full Python source for rules/generated.py>",
  "routines_script": "<full Python source for routines/generated.py>",
  "workflows_script": "<full Python source for workflows/generated.py>"
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MAP LAYOUT RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Each room may have at most ONE exit per direction (north/south/east/west/up/down/in/out).
- Stairs/lifts connect floors: the lower room has "up" and the upper room has "down".
- Use hallway rooms to branch corridors rather than giving one room many exits.
- Set z correctly: -1 for basement, 0 for ground, 1 for first floor, 2 for second, 3 for loft, etc.
- x/y give the 2-D position on that floor; they can repeat across floors (floors are independent planes).
- If the spec says "max 1 north, 1 south, 1 east, 1 west, 1 up, 1 down" enforce that strictly.
- If a spec lists a numbered set of rooms (e.g. "4 punishment nurseries") generate every one with unique IDs
  like punishment_nursery_1, punishment_nursery_2, etc.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCRIPTING CONVENTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Rules (rules/generated.py):
  - async functions named on_<event>(player, room, world, **kwargs)
  - Common events: player_enter, player_leave, player_action
  - Use player.flags (a plain dict) to track per-player state:
      player.flags["tag"] = "bad"
      player.flags["punishment_until"] = tick_count + 20
      player.flags.get("level", "yourself")
  - Use room.properties to read room metadata:
      if room.properties.get("room_type") == "punishment_nursery": ...
  - Call world.sessions.send(player.session_id, {"type": "message", "text": "..."})
    to narrate an event to a specific player.

Routines (routines/generated.py):
  - async run(world, tick_count)
  - Use tick_count % N to run every N ticks (tick ≈ 3 s at idle, ≈ 0.5 s at peak)
  - NPC shift scheduling: read npc.properties["shift"] to decide movement.
  - Move an NPC: npc.room_id = new_room_id (also update room entity_ids).
  - Send a room-wide message:
      for sid, pid in list(world.sessions._sessions.items()):
          p = world.players.get(pid)
          if p and p.room_id == room_id:
              await world.sessions.send(sid, {"type": "message", "text": "..."})

Workflows (workflows/generated.py):
  - STEPS = ["step_one", "step_two", ...]
  - async on_progress(player, step, world, **kwargs)
  - Triggered by scripts calling world.scripts.advance_workflow(wf_name, player=player, step=..., world=world)

For a detailed spec, write MEANINGFUL scripts that implement the described rules.
Use player.flags extensively for state machines (punishment levels, tags, room assignments, timers).
Implement all unique schedules, rules, and progression systems mentioned in the spec.
"""


async def build_world(spec_text: str, build_log: list) -> dict:
    """Call Claude with a theme or spec, return parsed world dict.

    build_log is a list that receives human-readable step entries so the
    caller can surface them to the admin UI.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        build_log.append("ERROR  No ANTHROPIC_API_KEY set in .env — cannot call Claude")
        raise ValueError("ANTHROPIC_API_KEY is not set")

    preview = spec_text[:200].replace("\n", " ")
    build_log.append(
        f"SEND   model=claude-opus-4-7  spec={len(spec_text)} chars  "
        f"preview: {preview!r}"
    )
    log.info("[builder] Sending spec to Claude (%d chars)", len(spec_text))

    client = anthropic.AsyncAnthropic(api_key=api_key)
    msg = await client.messages.create(
        model="claude-opus-4-7",
        max_tokens=16384,
        system=_SYSTEM,
        messages=[{"role": "user", "content": spec_text}],
    )
    raw = msg.content[0].text.strip()

    build_log.append(
        f"RECV   raw={len(raw)} chars  "
        f"stop_reason={msg.stop_reason}  "
        f"preview: {raw[:300].replace(chr(10), ' ')!r}"
    )
    log.info("[builder] Claude responded: %d chars, stop_reason=%s",
             len(raw), msg.stop_reason)

    # strip markdown fences if the model added them despite instructions
    stripped = raw
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1]
        stripped = stripped.rsplit("```", 1)[0].strip()
        build_log.append("PARSE  Stripped markdown fences from response")

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        build_log.append(
            f"ERROR  JSON parse failed at char {exc.pos}: {exc.msg}  "
            f"context: {stripped[max(0,exc.pos-60):exc.pos+60]!r}"
        )
        log.error("[builder] JSON parse failed: %s  near: %r",
                  exc, stripped[max(0,exc.pos-60):exc.pos+60])
        raise ValueError(f"World builder returned invalid JSON: {exc.msg}") from exc

    rooms = len(data.get("rooms", []))
    npcs  = len(data.get("npcs",  []))
    items = len(data.get("items", []))
    world_id = data.get("config", {}).get("id", "?")
    build_log.append(
        f"PARSE  JSON OK — world_id={world_id!r}  "
        f"rooms={rooms}  npcs={npcs}  items={items}"
    )
    log.info("[builder] JSON parsed: id=%s  rooms=%d  npcs=%d  items=%d",
             world_id, rooms, npcs, items)
    return data


def materialise_world(data: dict) -> Path:
    """Write a built world dict to disk and return the world directory path."""
    world_id = data["config"]["id"]
    world_dir = _DATA_ROOT / world_id
    scripts_dir = world_dir / "scripts"
    for subdir in ("rules", "routines", "workflows"):
        (scripts_dir / subdir).mkdir(parents=True, exist_ok=True)

    # config.json
    (world_dir / "config.json").write_text(
        json.dumps(data["config"], indent=2), encoding="utf-8"
    )

    # seed.py — rooms, zones, npcs, monsters, items
    lines = [
        "from world.zone import Zone, ZoneType",
        "from world.room import Room",
        "from entities.npc import NPC",
        "from entities.monster import Monster",
        "from entities.item import Item",
        "",
        "def seed(world):",
    ]

    for z in data.get("zones", []):
        zt = z.get("zone_type", "indoor").upper()
        lines.append(
            f"    world.map.add_zone(Zone(id={z['id']!r}, name={z['name']!r}, "
            f"zone_type=ZoneType.{zt}))"
        )

    entry_room_id = None
    for r in data.get("rooms", []):
        exits_repr = repr(r.get("exits", {}))
        props_repr = repr(r.get("properties", {}))
        z_val = r.get("z", 0)
        lines.append(
            f"    world.map.add_room(Room(id={r['id']!r}, name={r['name']!r}, "
            f"description={r['description']!r}, zone_id={r['zone_id']!r}, "
            f"x={r.get('x', 0)}, y={r.get('y', 0)}, z={z_val}, "
            f"exits={exits_repr}, properties={props_repr}))"
        )
        if r.get("entry"):
            entry_room_id = r["id"]
    if entry_room_id:
        lines.append(f"    world.map.set_entry_room({entry_room_id!r})")

    for n in data.get("npcs", []):
        dialogue_repr = repr(n.get("dialogue", []))
        props_repr = repr(n.get("properties", {}))
        lines.append(
            f"    world.npcs[{n['id']!r}] = NPC(id={n['id']!r}, name={n['name']!r}, "
            f"description={n['description']!r}, room_id={n['room_id']!r}, "
            f"dialogue={dialogue_repr}, properties={props_repr})"
        )

    for m in data.get("monsters", []):
        lines.append(
            f"    world.spawn_monster(Monster(id={m['id']!r}, name={m['name']!r}, "
            f"description={m['description']!r}, room_id={m['room_id']!r}, "
            f"hp={m.get('hp', 20)}, max_hp={m.get('hp', 20)}, "
            f"attack={m.get('attack', 5)}, defence={m.get('defence', 2)}))"
        )

    for item in data.get("items", []):
        props_repr = repr(item.get("properties", {}))
        room_arg = f"room_id={item['room_id']!r}" if item.get("room_id") else "room_id=None"
        lines.append(
            f"    world.items[{item['id']!r}] = Item(id={item['id']!r}, "
            f"name={item['name']!r}, description={item['description']!r}, "
            f"item_type={item.get('item_type', 'misc')!r}, {room_arg}, "
            f"properties={props_repr})"
        )

    (world_dir / "seed.py").write_text("\n".join(lines), encoding="utf-8")

    # scripts
    _write_script(scripts_dir / "rules"     / "generated.py", data.get("rules_script"))
    _write_script(scripts_dir / "routines"  / "generated.py", data.get("routines_script"))
    _write_script(scripts_dir / "workflows" / "generated.py", data.get("workflows_script"))

    log.info("World materialised: %s → %s", world_id, world_dir)
    return world_dir


def _write_script(path: Path, source: str | None):
    if not source:
        return
    path.write_text(source, encoding="utf-8")
