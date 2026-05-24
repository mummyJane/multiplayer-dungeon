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
You are a game world designer. You will receive either:
  A) A short theme description (1-3 sentences), or
  B) A detailed world specification document.

In both cases, return ONLY a valid JSON object — no markdown fences, no commentary.
For a detailed spec, extract as much structure as possible; invent sensible defaults for anything not specified.

Required JSON shape:
{
  "config": {
    "id": "<lowercase-slug>",
    "name": "<display name>",
    "description": "<1-2 sentences>",
    "max_players": <int>,
    "ollama_model": "llama3"
  },
  "zones": [
    {"id": "<slug>", "name": "<name>", "zone_type": "outdoor|indoor|dungeon|building"}
  ],
  "rooms": [
    {
      "id": "<slug>",
      "name": "<name>",
      "description": "<2-3 sentences, flavourful>",
      "zone_id": "<zone id>",
      "x": <int>, "y": <int>,
      "exits": {"north": "<room_id>", ...},
      "entry": true    // mark exactly ONE room as the player entry point
    }
  ],
  "npcs": [
    {
      "id": "<slug>", "name": "<name>", "description": "<sentence>",
      "room_id": "<room_id>", "role": "<role description>"
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
      "room_id": "<room_id or null>"
    }
  ],
  "rules_script": "<full Python source for rules/generated.py>",
  "routines_script": "<full Python source for routines/generated.py>",
  "workflows_script": "<full Python source for workflows/generated.py>"
}

Python script conventions:
  rules/generated.py    — define async functions named on_<event>(player, room, world)
                          Common events: player_enter, player_leave, player_action
  routines/generated.py — define async run(world, tick_count)
                          Use tick_count % N to run every N ticks
  workflows/generated.py — define async on_progress(player, step, world)
                          and a list STEPS = [...]

For a detailed spec document, generate MEANINGFUL scripts that actually implement
the described rules, schedules, and progression systems — not empty stubs.
Use world.players, world.npcs, world.map, world.sessions, world.scripts as needed.
Player objects have: id, name, room_id, hp, inventory, and a __dict__ for custom flags.
"""


async def build_world(spec_text: str) -> dict:
    """Call Claude with a theme or spec, return parsed world dict."""
    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    msg = await client.messages.create(
        model="claude-opus-4-7",
        max_tokens=8192,
        system=_SYSTEM,
        messages=[{"role": "user", "content": spec_text}],
    )
    raw = msg.content[0].text.strip()
    # strip markdown fences if the model added them despite instructions
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error("Claude returned non-JSON (first 400 chars): %s", raw[:400])
        raise ValueError("World builder returned invalid JSON") from exc


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
        lines.append(
            f"    world.map.add_room(Room(id={r['id']!r}, name={r['name']!r}, "
            f"description={r['description']!r}, zone_id={r['zone_id']!r}, "
            f"x={r.get('x', 0)}, y={r.get('y', 0)}, exits={exits_repr}))"
        )
        if r.get("entry"):
            entry_room_id = r["id"]
    if entry_room_id:
        lines.append(f"    world.map.set_entry_room({entry_room_id!r})")

    for n in data.get("npcs", []):
        dialogue_repr = repr(n.get("dialogue", []))
        lines.append(
            f"    world.npcs[{n['id']!r}] = NPC(id={n['id']!r}, name={n['name']!r}, "
            f"description={n['description']!r}, room_id={n['room_id']!r}, "
            f"dialogue={dialogue_repr})"
        )

    for m in data.get("monsters", []):
        lines.append(
            f"    world.spawn_monster(Monster(id={m['id']!r}, name={m['name']!r}, "
            f"description={m['description']!r}, room_id={m['room_id']!r}, "
            f"hp={m.get('hp', 20)}, max_hp={m.get('hp', 20)}, "
            f"attack={m.get('attack', 5)}, defence={m.get('defence', 2)}))"
        )

    for item in data.get("items", []):
        room_id = item.get("room_id") or "None"
        room_arg = f"room_id={item['room_id']!r}" if item.get("room_id") else "room_id=None"
        lines.append(
            f"    world.items[{item['id']!r}] = Item(id={item['id']!r}, "
            f"name={item['name']!r}, description={item['description']!r}, "
            f"item_type={item.get('item_type','misc')!r}, {room_arg})"
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
