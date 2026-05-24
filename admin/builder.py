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

CRITICAL JSON SAFETY RULES — violations cause parse errors:
1. Every double-quote character inside a string value MUST be escaped as \"
   WRONG:  "dialogue": ["She said "hello" to the baby."]
   RIGHT:  "dialogue": ["She said \"hello\" to the baby."]
2. Never put raw newlines inside string values — use \n if needed.
3. No trailing commas before } or ].

CRITICAL PYTHON SCRIPT SAFETY RULES — violations cause SyntaxError or ModuleNotFoundError:
1. ALWAYS use double-quoted strings in Python: "text" — NEVER single-quoted 'text'
   Reason: apostrophes in English words like "you'll", "it's", "don't" will break
   a single-quoted string but are safe inside double quotes.
   WRONG:  await _send(world, player, 'You\'ll be tagged bad.')
   RIGHT:  await _send(world, player, "You'll be tagged bad.")
2. To embed a double-quote inside a string, escape it: "She said \"hello\""
3. Never write a string literal that spans multiple lines — use \n inside instead.
4. Every opened string MUST be closed on the same line.
5. ALL import statements MUST be at the TOP of the file (module level) — NEVER inside a
   function body. Lazy imports inside functions fail at runtime because the module
   namespace is only available at load time.
   WRONG:  async def _hourly_announce(world):
               from rules.generated import _rooms_of_type   # ← CRASHES at runtime
   RIGHT:  from rules.generated import _rooms_of_type       # ← top of file, always

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
World API — use these in all scripts:
  world.rooms                  — dict[room_id, Room]  (use .get(id) or .values())
  world.players                — dict[player_id, Player]
  world.npcs                   — dict[npc_id, NPC]
  world.map.get_room(id)       — same as world.rooms.get(id)
  world.sessions.send(sid, {}) — send JSON to one session
  world.broadcast_to_room(room_id, text)  — send to ALL players in a room
  player.session_id            — use this to send a message to one player
  player.flags                 — plain dict for per-player state
  room.properties              — dict set in seed.py for room metadata

Cross-script imports ARE supported (scripts load in order: rules → routines → workflows):
  # In routines/generated.py you may write:
  from rules.generated import find_free_room, _rooms_of_type

Rules (rules/generated.py):
  - async functions named on_<event>(player, room, world, **kwargs)
  - Common events: player_enter, player_leave, player_action
  - Use player.flags for state: player.flags["tag"] = "bad"
  - Narrate to one player:
      await world.sessions.send(player.session_id, {"type": "message", "text": "..."})

Routines (routines/generated.py):
  - async run(world, tick_count)
  - tick ≈ 3 s idle, ≈ 0.5 s busy. Use tick_count % N for every-N-tick actions.
  - NPC shift scheduling: read npc.properties["shift"] / "shift_start" / "shift_end"
  - Move an NPC: npc.room_id = new_room_id
  - Broadcast to a room:
      await world.broadcast_to_room(room_id, "A nanny arrives with a bottle.")
  - Send to one player:
      await world.sessions.send(player.session_id, {"type": "message", "text": "..."})

Workflows (workflows/generated.py):
  - STEPS = ["step_one", ...]
  - async on_progress(player, step, world, **kwargs)

For a detailed spec, write MEANINGFUL scripts that implement the described rules.
Use player.flags for all state machines (punishment levels, tags, timers, room assignments).
Implement all schedules, feeding rules, and progression systems mentioned in the spec.
"""


def _repair_json_inline(raw: str) -> str:
    """Fix the two most common LLM JSON mistakes without any library.

    1. Literal newlines / carriage returns / tabs inside string values.
    2. Trailing commas before ] or }.
    """
    import re
    result: list[str] = []
    in_string = False
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == '\\' and in_string:
            # Escape sequence — keep both chars verbatim.
            result.append(ch)
            i += 1
            if i < len(raw):
                result.append(raw[i])
                i += 1
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
        elif in_string and ch == '\n':
            result.append('\\n')
        elif in_string and ch == '\r':
            result.append('\\r')
        elif in_string and ch == '\t':
            result.append('\\t')
        else:
            result.append(ch)
        i += 1
    cleaned = ''.join(result)
    # Remove trailing commas before } or ]
    cleaned = re.sub(r',(\s*[}\]])', r'\1', cleaned)
    return cleaned


def _parse_with_repair(raw: str) -> tuple[dict | None, str]:
    """Try to parse JSON, applying progressively heavier repair steps.

    Returns (data, repair_note) — repair_note is empty string on clean parse.
    Returns (None, "") if all strategies fail.
    """
    # Strategy 1 — parse as-is
    try:
        return json.loads(raw), ""
    except json.JSONDecodeError as exc1:
        log.debug("JSON parse pass 1 failed: %s", exc1)

    # Strategy 2 — inline fix: literal newlines + trailing commas
    try:
        fixed = _repair_json_inline(raw)
        return json.loads(fixed), "inline fix (literal newlines / trailing commas)"
    except json.JSONDecodeError as exc2:
        log.debug("JSON parse pass 2 failed: %s", exc2)

    # Strategy 3 — json-repair library (handles unescaped quotes, truncation, etc.)
    try:
        from json_repair import repair_json
        repaired = repair_json(raw, return_objects=True)
        if isinstance(repaired, dict) and repaired:
            return repaired, "json-repair library (unescaped quotes / structural issues)"
        # repair_json may return a string when return_objects isn't supported
        if isinstance(repaired, str):
            return json.loads(repaired), "json-repair library"
    except ImportError:
        log.warning("[builder] json-repair not installed — run: pip install json-repair")
    except Exception as exc3:
        log.debug("JSON parse pass 3 (json-repair) failed: %s", exc3)

    return None, ""


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
    # Streaming is required for large outputs (65K tokens can take >10 minutes).
    async with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=65536,
        system=_SYSTEM,
        messages=[{"role": "user", "content": spec_text}],
    ) as stream:
        raw = await stream.get_final_text()
        msg = await stream.get_final_message()
    raw = raw.strip()

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

    data, repair_note = _parse_with_repair(stripped)
    if data is None:
        ctx = stripped[max(0, 15780):15900] if len(stripped) > 15780 else stripped[-200:]
        build_log.append(
            f"ERROR  JSON parse failed — all repair strategies exhausted.  "
            f"context near error: {ctx!r}"
        )
        log.error("[builder] JSON unrecoverable.  context: %r", ctx)
        raise ValueError("World builder returned invalid JSON (all repair strategies failed)")
    if repair_note:
        build_log.append(f"REPAIR {repair_note}")
        log.info("[builder] JSON repaired: %s", repair_note)

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
            f"exits={exits_repr}, properties={props_repr}, creator="claude_api"))"
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
            f"dialogue={dialogue_repr}, properties={props_repr}, creator="claude_api")"
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
            f"properties={props_repr}, creator="claude_api")"
        )

    (world_dir / "seed.py").write_text("\n".join(lines), encoding="utf-8")

    # scripts — validate syntax before writing; skip broken ones
    script_errors: list[str] = []
    for cat, key in [("rules", "rules_script"), ("routines", "routines_script"),
                     ("workflows", "workflows_script")]:
        src = data.get(key)
        if src:
            err = _write_script(scripts_dir / cat / "generated.py", src)
            if err:
                script_errors.append(f"{cat}: {err}")

    log.info("World materialised: %s → %s", world_id, world_dir)
    return world_dir, script_errors


def _write_script(path: Path, source: str) -> str | None:
    """Write a Python script to disk, always.

    If the source has a SyntaxError a warning comment is prepended so the admin
    editor shows the problem clearly — the file is still written so users can fix
    it via the script editor rather than losing it entirely.
    Returns an error string on SyntaxError, or None on success.
    """
    banner = "# Generated by Claude admin builder — edit with care\n"
    src = banner + source if not source.lstrip().startswith("#") else source
    syntax_err = None
    try:
        compile(src, str(path), "exec")
    except SyntaxError as exc:
        syntax_err = f"SyntaxError line {exc.lineno}: {exc.msg}"
        log.warning("[builder] %s has %s — written anyway for manual repair",
                    path.name, syntax_err)
        # Prepend a visible error comment so it shows at the top of the editor
        src = f"# !! SYNTAX ERROR — fix before this script will load\n# !! {syntax_err}\n\n" + src
    path.write_text(src, encoding="utf-8")
    return syntax_err


# ── world expansion ────────────────────────────────────────────────────────────

_SYSTEM_EXPAND = """\
You are expanding an existing game world in a real-time multiplayer text RPG engine.
You will receive a description of the CURRENT world (rooms, NPCs, items) and a spec for NEW content to add.

Return ONLY a valid JSON object — no markdown fences, no commentary.

CRITICAL JSON SAFETY RULES (same as world builder):
1. Every double-quote inside a string value MUST be escaped as \"
2. Never put raw newlines inside string values — use \\n if needed.
3. No trailing commas before } or ].

CRITICAL PYTHON SCRIPT SAFETY RULES:
1. ALWAYS use double-quoted strings — NEVER single-quoted.
2. ALL import statements MUST be at the top of the file (module level).
3. Every opened string MUST be closed on the same line.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXPANSION JSON SHAPE  (do NOT include a "config" key)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "zones": [...],      // new zones only — omit if no new zones needed
  "rooms": [
    {
      "id": "<NEW slug — MUST NOT duplicate any existing room ID>",
      "name": "<name>",
      "description": "<2-3 sentences>",
      "zone_id": "<existing or new zone_id>",
      "x": <int>, "y": <int>, "z": <int>,
      "exits": {
        "north": "<room_id>",     // may reference EXISTING room IDs to connect new area
        "up": "<room_id>"
      },
      "properties": {}
    }
  ],
  "npcs": [
    {
      "id": "<NEW slug>",
      "name": "<name>",
      "description": "<sentence>",
      "room_id": "<new or existing room_id>",
      "dialogue": ["<line>", "..."],
      "properties": {}
    }
  ],
  "items": [
    {
      "id": "<NEW slug>",
      "name": "<name>",
      "description": "<sentence>",
      "item_type": "clothing|consumable|misc|weapon|armour|fixture",
      "room_id": "<new or existing room_id or null>",
      "properties": {}
    }
  ],
  "rules_script":    "<optional Python — new rules handlers only>",
  "routines_script": "<optional Python — new routine additions only>",
  "workflows_script": "<optional Python>"
}

RULES:
- Generate ONLY new content. NEVER duplicate existing IDs.
- New room exits may connect to existing rooms (use their IDs) — this creates physical links.
- If an existing room should gain an exit INTO the new area, include that in "connect_exits":
  "connect_exits": {"existing_room_id": {"direction": "new_room_id"}}
- Scripts should import from existing rules.generated if needed (at module top level).
"""


def _world_context_summary(world) -> str:
    """Produce a compact text summary of the current world for the expansion prompt."""
    lines = [
        f"WORLD: {world.config.id!r}  name={world.config.name!r}",
        f"description: {world.config.description}",
        "",
        f"ROOMS ({len(world.map._rooms)}):",
    ]
    for r in sorted(world.map._rooms.values(), key=lambda x: (x.z, x.y, x.x)):
        exits = ", ".join(f"{d}→{t}" for d, t in r.exits.items()) or "none"
        lines.append(f"  {r.id!r:40s}  z={r.z}  [{exits}]  — {r.name}")

    lines += ["", f"NPCs ({len(world.npcs)}):"]
    for n in sorted(world.npcs.values(), key=lambda x: x.name):
        lines.append(f"  {n.id!r:40s}  room={n.room_id!r}  — {n.name}")

    lines += ["", f"ITEMS ({len(world.items)}):"]
    for i in sorted(world.items.values(), key=lambda x: x.name):
        lines.append(f"  {i.id!r:40s}  room={str(i.room_id)!r}  — {i.name}")

    return "\n".join(lines)


async def expand_world(world, spec_text: str, build_log: list) -> dict:
    """Call Claude to generate expansion content for an existing world.

    world — live WorldInstance (used to build context summary).
    Returns a partial world dict (no 'config' key) with new rooms/NPCs/items/scripts.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        build_log.append("ERROR  No ANTHROPIC_API_KEY set — cannot call Claude")
        raise ValueError("ANTHROPIC_API_KEY is not set")

    context = _world_context_summary(world)
    user_msg = (
        f"{context}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"EXPANSION REQUEST:\n{spec_text}"
    )

    build_log.append(
        f"SEND   model=claude-opus-4-7  expand for={world.config.id!r}  "
        f"spec={len(spec_text)} chars"
    )
    log.info("[builder] Sending expansion request for %s (%d chars)", world.config.id, len(spec_text))

    client = anthropic.AsyncAnthropic(api_key=api_key)
    async with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=65536,
        system=_SYSTEM_EXPAND,
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        raw = await stream.get_final_text()
        msg = await stream.get_final_message()
    raw = raw.strip()

    build_log.append(
        f"RECV   raw={len(raw)} chars  stop_reason={msg.stop_reason}"
    )

    stripped = raw
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    data, repair_note = _parse_with_repair(stripped)
    if data is None:
        build_log.append("ERROR  JSON parse failed — all repair strategies exhausted")
        raise ValueError("Expansion builder returned invalid JSON")
    if repair_note:
        build_log.append(f"REPAIR {repair_note}")

    rooms = len(data.get("rooms", []))
    npcs  = len(data.get("npcs", []))
    items = len(data.get("items", []))
    build_log.append(f"PARSE  JSON OK — rooms={rooms}  npcs={npcs}  items={items}")
    return data


def _load_manual(world_id: str) -> dict:
    path = _DATA_ROOT / world_id / "manual.json"
    if not path.exists():
        return {"rooms": {}, "npcs": {}, "items": {}, "deleted": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_manual(world_id: str, data: dict):
    path = _DATA_ROOT / world_id / "manual.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def materialise_expansion(world_id: str, data: dict) -> tuple[Path, list[str]]:
    """Persist expansion data to disk:
    - New rooms/NPCs/items added to manual.json as 'add' actions.
    - Exits to add to existing rooms stored in manual.json room edits.
    - New scripts saved as rules_expand_N.py / routines_expand_N.py etc.
    Returns (world_dir, script_errors).
    """
    world_dir = _DATA_ROOT / world_id
    scripts_dir = world_dir / "scripts"
    manual = _load_manual(world_id)

    for r in data.get("zones", []):
        pass  # zones don't need persistence (added live only)

    for r in data.get("rooms", []):
        manual["rooms"][r["id"]] = {
            "_action": "add",
            "name": r.get("name", r["id"]),
            "description": r.get("description", ""),
            "zone_id": r.get("zone_id", "default"),
            "x": r.get("x", 0), "y": r.get("y", 0), "z": r.get("z", 0),
            "exits": r.get("exits", {}),
            "properties": r.get("properties", {}),
            "creator": "claude_api",
        }

    # connect_exits: patch existing rooms to point at new rooms
    for existing_id, exit_patch in data.get("connect_exits", {}).items():
        if existing_id not in manual["rooms"]:
            manual["rooms"][existing_id] = {"_action": "edit", "exits": {}}
        entry = manual["rooms"][existing_id]
        if "_action" not in entry:
            entry["_action"] = "edit"
        if "exits" not in entry:
            entry["exits"] = {}
        entry["exits"].update(exit_patch)

    for n in data.get("npcs", []):
        manual["npcs"][n["id"]] = {
            "_action": "add",
            "name": n.get("name", n["id"]),
            "description": n.get("description", ""),
            "room_id": n.get("room_id", ""),
            "dialogue": n.get("dialogue", []),
            "properties": n.get("properties", {}),
            "creator": "claude_api",
        }

    for i in data.get("items", []):
        manual["items"][i["id"]] = {
            "_action": "add",
            "name": i.get("name", i["id"]),
            "description": i.get("description", ""),
            "item_type": i.get("item_type", "misc"),
            "room_id": i.get("room_id"),
            "properties": i.get("properties", {}),
            "creator": "claude_api",
        }

    _save_manual(world_id, manual)

    # expansion scripts — numbered to avoid overwriting existing ones
    script_errors: list[str] = []
    for cat, key in [("rules", "rules_script"), ("routines", "routines_script"),
                     ("workflows", "workflows_script")]:
        src = data.get(key)
        if not src or not src.strip():
            continue
        cat_dir = scripts_dir / cat
        cat_dir.mkdir(parents=True, exist_ok=True)
        n = len(list(cat_dir.glob(f"{cat}_expand_*.py"))) + 1
        path = cat_dir / f"{cat}_expand_{n:03d}.py"
        err = _write_script(path, src)
        if err:
            script_errors.append(f"{cat}_expand_{n:03d}: {err}")

    log.info("Expansion materialised for %s: %d rooms, %d npcs, %d items",
             world_id, len(data.get("rooms", [])),
             len(data.get("npcs", [])), len(data.get("items", [])))
    return world_dir, script_errors
