"""Claude API world builder — takes a theme description and generates world content."""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path

import anthropic

log = logging.getLogger(__name__)

_DATA_ROOT = Path(__file__).parent.parent / "data" / "worlds"
_CLIENT = None


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    return _CLIENT


_SYSTEM = """\
You are a game world designer. Given a theme description, generate a complete game world definition.

Return ONLY a JSON object with this exact structure (no markdown, no extra text):
{
  "config": {
    "id": "<slug, lowercase, hyphens>",
    "name": "<display name>",
    "description": "<1-2 sentences>",
    "max_players": 50,
    "ollama_model": "llama3"
  },
  "rooms": [
    {
      "id": "<slug>",
      "name": "<room name>",
      "description": "<2-3 sentences>",
      "zone_id": "<zone_slug>",
      "x": <int>,
      "y": <int>,
      "exits": {"north": "<room_id>", ...},
      "entry": true  // mark exactly one room as the entry point
    }
  ],
  "zones": [
    {"id": "<slug>", "name": "<name>", "zone_type": "outdoor|indoor|dungeon|building"}
  ],
  "npcs": [
    {"id": "<slug>", "name": "<name>", "description": "<sentence>", "room_id": "<room_id>"}
  ],
  "monsters": [
    {"id": "<slug>", "name": "<name>", "description": "<sentence>", "room_id": "<room_id>",
     "hp": <int>, "attack": <int>, "defence": <int>}
  ],
  "rules_script": "<python source for rules/generated.py>",
  "routines_script": "<python source for routines/generated.py>"
}
"""


async def build_world(theme: str) -> dict:
    """Call Claude API with a theme description and return parsed world dict."""
    msg = _client().messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        system=_SYSTEM,
        messages=[{"role": "user", "content": f"Theme: {theme}"}],
    )
    raw = msg.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error("Claude returned non-JSON: %s", raw[:200])
        raise ValueError("World builder returned invalid JSON") from exc


def materialise_world(data: dict) -> Path:
    """Write a built world dict to disk. Returns the world directory path."""
    world_id = data["config"]["id"]
    world_dir = _DATA_ROOT / world_id
    scripts_dir = world_dir / "scripts"
    (scripts_dir / "rules").mkdir(parents=True, exist_ok=True)
    (scripts_dir / "routines").mkdir(parents=True, exist_ok=True)
    (scripts_dir / "workflows").mkdir(parents=True, exist_ok=True)

    # config.json
    (world_dir / "config.json").write_text(
        json.dumps(data["config"], indent=2), encoding="utf-8"
    )

    # seed.py — rooms, zones, npcs, monsters
    seed_lines = [
        "from world.zone import Zone, ZoneType",
        "from world.room import Room",
        "from entities.npc import NPC",
        "from entities.monster import Monster",
        "",
        "def seed(world):",
    ]
    for z in data.get("zones", []):
        zt = z.get("zone_type", "outdoor").upper()
        seed_lines.append(
            f"    world.map.add_zone(Zone(id={z['id']!r}, name={z['name']!r}, "
            f"zone_type=ZoneType.{zt}))"
        )
    entry_room_id = None
    for r in data.get("rooms", []):
        exits_repr = repr(r.get("exits", {}))
        seed_lines.append(
            f"    world.map.add_room(Room(id={r['id']!r}, name={r['name']!r}, "
            f"description={r['description']!r}, zone_id={r['zone_id']!r}, "
            f"x={r.get('x', 0)}, y={r.get('y', 0)}, exits={exits_repr}))"
        )
        if r.get("entry"):
            entry_room_id = r["id"]
    if entry_room_id:
        seed_lines.append(f"    world.map.set_entry_room({entry_room_id!r})")
    for n in data.get("npcs", []):
        seed_lines.append(
            f"    world.npcs[{n['id']!r}] = NPC(id={n['id']!r}, name={n['name']!r}, "
            f"description={n['description']!r}, room_id={n['room_id']!r})"
        )
    for m in data.get("monsters", []):
        seed_lines.append(
            f"    world.spawn_monster(Monster(id={m['id']!r}, name={m['name']!r}, "
            f"description={m['description']!r}, room_id={m['room_id']!r}, "
            f"hp={m.get('hp', 20)}, max_hp={m.get('hp', 20)}, "
            f"attack={m.get('attack', 5)}, defence={m.get('defence', 2)}))"
        )
    (world_dir / "seed.py").write_text("\n".join(seed_lines), encoding="utf-8")

    # generated scripts
    if data.get("rules_script"):
        (scripts_dir / "rules" / "generated.py").write_text(
            data["rules_script"], encoding="utf-8"
        )
    if data.get("routines_script"):
        (scripts_dir / "routines" / "generated.py").write_text(
            data["routines_script"], encoding="utf-8"
        )

    log.info("World materialised: %s at %s", world_id, world_dir)
    return world_dir
