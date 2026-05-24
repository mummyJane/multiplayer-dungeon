"""Admin HTTP routes — world management and Claude API world builder."""
from __future__ import annotations
import os
import logging
from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pathlib import Path

_DATA_ROOT = Path(__file__).parent.parent / "data" / "worlds"

log = logging.getLogger(__name__)
admin_router = APIRouter(prefix="/admin")

_WEB_DIR = Path(__file__).parent.parent / "web"
_ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "changeme")

_MAX_UPLOAD_BYTES = 512 * 1024  # 512 KB


def _require_admin(x_admin_key: str = Header(default="")):
    if x_admin_key != _ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin key")


# ── models ────────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    """Short theme description or full spec text, pasted directly."""
    text: str


class WorldConfigRequest(BaseModel):
    id: str
    name: str
    description: str = ""
    max_players: int = 50
    ollama_model: str = "llama3"


class ConfigPatch(BaseModel):
    name: str = ""
    description: str = ""
    max_players: int = 0
    ollama_model: str = ""


class ScriptsSave(BaseModel):
    rules: str = ""
    routines: str = ""
    workflows: str = ""


# ── shared world-creation helper ──────────────────────────────────────────────

async def _build_and_load(spec_text: str):
    """Build from spec_text, materialise to disk, live-load, and return summary.

    Always returns a dict containing a 'build_log' list of step strings so
    the admin UI can show exactly what happened (or went wrong).
    Raises HTTPException with the log attached on failure.
    """
    from admin.builder import build_world, materialise_world
    from api.state import registry
    from worlds.instance import WorldConfig
    from worlds.registry import _run_seeder
    import traceback

    build_log: list[str] = []

    # ── Step 1: call Claude ───────────────────────────────────────────────────
    try:
        data = await build_world(spec_text, build_log)
    except Exception as exc:
        build_log.append(f"ABORT  Claude call failed: {exc}")
        log.exception("[admin] build_world failed")
        raise HTTPException(500, detail={"error": str(exc), "build_log": build_log})

    # ── Step 2: write files to disk ───────────────────────────────────────────
    try:
        world_dir, script_errors = materialise_world(data)
        build_log.append(f"WRITE  World files written to {world_dir}")
        for se in script_errors:
            build_log.append(f"WARN   Script skipped (syntax error): {se}")
        log.info("[admin] materialise_world → %s", world_dir)
    except Exception as exc:
        build_log.append(f"ABORT  materialise_world failed: {exc}")
        log.exception("[admin] materialise_world failed")
        raise HTTPException(500, detail={"error": str(exc), "build_log": build_log})

    # ── Step 3: live-load into registry ──────────────────────────────────────
    cfg_data = data["config"]
    config = WorldConfig(
        id=cfg_data["id"],
        name=cfg_data["name"],
        description=cfg_data.get("description", ""),
        max_players=cfg_data.get("max_players", 50),
        ollama_model=cfg_data.get("ollama_model", "llama3"),
    )
    try:
        world = registry.create(config)
        build_log.append(f"LOAD   World '{config.id}' registered in memory")
    except ValueError as exc:
        build_log.append(f"ABORT  Registry error: {exc}")
        raise HTTPException(409, detail={"error": str(exc), "build_log": build_log})

    # ── Step 4: load scripts ──────────────────────────────────────────────────
    try:
        world.scripts.load(world_dir / "scripts")
        build_log.append(f"LOAD   Scripts loaded from {world_dir / 'scripts'}")
    except Exception as exc:
        build_log.append(f"WARN   Script load error (world still created): {exc}")
        log.warning("[admin] script load error: %s", exc)

    # ── Step 5: run seeder ────────────────────────────────────────────────────
    seed_path = world_dir / "seed.py"
    if seed_path.exists():
        try:
            _run_seeder(seed_path, world)
            rooms_seeded = len(world.map._rooms)
            npcs_seeded  = len(world.npcs)
            build_log.append(
                f"SEED   seed.py ran OK — "
                f"{rooms_seeded} rooms, {npcs_seeded} NPCs in world"
            )
        except Exception as exc:
            tb = traceback.format_exc()
            build_log.append(f"WARN   seed.py error (world still running): {exc}")
            build_log.append(f"       {tb.splitlines()[-1]}")
            log.warning("[admin] seed.py error:\n%s", tb)

    world.start_loop()
    build_log.append("START  Game loop started")

    rooms  = len(data.get("rooms", []))
    npcs   = len(data.get("npcs", []))
    items  = len(data.get("items", []))
    return {
        "world_id": config.id,
        "name":     config.name,
        "rooms":    rooms,
        "npcs":     npcs,
        "items":    items,
        "build_log": build_log,
    }


# ── routes ────────────────────────────────────────────────────────────────────

@admin_router.get("/", response_class=HTMLResponse)
async def admin_ui():
    return (_WEB_DIR / "admin.html").read_text(encoding="utf-8")


@admin_router.get("/worlds")
async def list_worlds(_=Depends(_require_admin)):
    from api.state import registry
    return [
        {
            "id": w.id,
            "name": w.name,
            "description": w.config.description,
            "players": w.player_count,
            "max_players": w.config.max_players,
        }
        for w in registry.all()
    ]


@admin_router.post("/worlds/generate")
async def generate_world(req: GenerateRequest, _=Depends(_require_admin)):
    """Generate a world from pasted text (theme or full spec)."""
    if not req.text.strip():
        raise HTTPException(400, "Text is empty")
    return await _build_and_load(req.text)


@admin_router.post("/worlds/upload")
async def upload_world_spec(
    file: UploadFile = File(...),
    _=Depends(_require_admin),
):
    """Generate a world from an uploaded text file (.txt, .md, etc.)."""
    content = await file.read(_MAX_UPLOAD_BYTES)
    if len(content) == _MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 512 KB)")
    try:
        spec_text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "File must be UTF-8 plain text")
    if not spec_text.strip():
        raise HTTPException(400, "File is empty")
    return await _build_and_load(spec_text)


@admin_router.post("/worlds/manual")
async def create_world_manual(req: WorldConfigRequest, _=Depends(_require_admin)):
    """Create a blank world (admin fills rooms/scripts by hand)."""
    from api.state import registry
    from worlds.instance import WorldConfig

    config = WorldConfig(
        id=req.id, name=req.name,
        description=req.description,
        max_players=req.max_players,
        ollama_model=req.ollama_model,
    )
    world = registry.create(config)
    registry.save_config(world)
    world.start_loop()
    return {"world_id": config.id, "name": config.name}


@admin_router.delete("/worlds/{world_id}")
async def delete_world(world_id: str, _=Depends(_require_admin)):
    from api.state import registry
    registry.remove(world_id)
    return {"removed": world_id}


@admin_router.post("/worlds/{world_id}/reload-scripts")
async def reload_scripts(world_id: str, _=Depends(_require_admin)):
    from api.state import registry
    from scripting.context import ScriptContext

    world = registry.get(world_id)
    if world is None:
        raise HTTPException(404, "World not found")
    scripts_dir = _DATA_ROOT / world_id / "scripts"
    world.scripts = ScriptContext(world_id)
    world.scripts.load(scripts_dir)
    return {"reloaded": world_id}


# ── world detail (view) ───────────────────────────────────────────────────────

@admin_router.get("/worlds/{world_id}/detail")
async def world_detail(world_id: str, _=Depends(_require_admin)):
    from api.state import registry
    world = registry.get(world_id)
    if world is None:
        raise HTTPException(404, "World not found")

    rooms = [
        {
            "id":           r.id,
            "name":         r.name,
            "description":  r.description[:120] + ("…" if len(r.description) > 120 else ""),
            "zone_id":      r.zone_id,
            "x": r.x, "y": r.y, "z": r.z,
            "exits":        r.exits,
            "properties":   r.properties,
            "gm_generated": r.gm_generated,
        }
        for r in sorted(world.map._rooms.values(), key=lambda r: (r.z, r.y, r.x))
    ]
    npcs = [
        {
            "id":           n.id,
            "name":         n.name,
            "description":  n.description,
            "room_id":      n.room_id,
            "properties":   n.properties,
            "gm_generated": n.gm_generated,
        }
        for n in sorted(world.npcs.values(), key=lambda n: n.name)
    ]
    items = [
        {
            "id":           i.id,
            "name":         i.name,
            "item_type":    i.item_type,
            "room_id":      i.room_id or "—",
            "properties":   i.properties,
            "gm_generated": i.gm_generated,
        }
        for i in sorted(world.items.values(), key=lambda i: i.name)
    ]
    return {
        "config": {
            "id":          world.config.id,
            "name":        world.config.name,
            "description": world.config.description,
            "max_players": world.config.max_players,
            "ollama_model":world.config.ollama_model,
        },
        "rooms":        rooms,
        "npcs":         npcs,
        "items":        items,
        "player_count": world.player_count,
    }


# ── script view / edit ────────────────────────────────────────────────────────

@admin_router.get("/worlds/{world_id}/scripts")
async def get_scripts(world_id: str, _=Depends(_require_admin)):
    """Return content of generated.py for each script category."""
    scripts_dir = _DATA_ROOT / world_id / "scripts"
    result = {}
    for cat in ("rules", "routines", "workflows"):
        path = scripts_dir / cat / "generated.py"
        result[cat] = path.read_text(encoding="utf-8") if path.exists() else ""
    return result


@admin_router.put("/worlds/{world_id}/scripts")
async def save_scripts(world_id: str, req: ScriptsSave, _=Depends(_require_admin)):
    """Write one or more generated.py files then reload scripts."""
    from api.state import registry
    from scripting.context import ScriptContext

    scripts_dir = _DATA_ROOT / world_id / "scripts"
    saved = []
    errors = []

    for cat, source in [("rules", req.rules), ("routines", req.routines),
                        ("workflows", req.workflows)]:
        if not source.strip():
            continue
        path = scripts_dir / cat / "generated.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(source, encoding="utf-8")
            saved.append(f"{cat}/generated.py")
        except Exception as exc:
            errors.append(f"{cat}: {exc}")

    world = registry.get(world_id)
    reloaded = False
    if world and saved:
        world.scripts = ScriptContext(world_id)
        try:
            world.scripts.load(scripts_dir)
            reloaded = True
        except Exception as exc:
            errors.append(f"reload: {exc}")

    return {"saved": saved, "reloaded": reloaded, "errors": errors}


# ── active players ───────────────────────────────────────────────────────────

@admin_router.get("/worlds/{world_id}/players")
async def world_players(world_id: str, _=Depends(_require_admin)):
    from api.state import registry
    world = registry.get(world_id)
    if world is None:
        raise HTTPException(404, "World not found")
    result = []
    for player in world.players.values():
        room = world.map.get_room(player.room_id)
        room_name = room.name if room else player.room_id
        worn_names = {slot: world.items[i].name
                      for slot, i in player.worn.items() if i in world.items}
        effects = sorted(player.worn_effects(world.items))
        active_flags = {k: v for k, v in player.flags.items()
                        if v not in (False, None, 0, "", [])}
        result.append({
            "id": player.id,
            "name": player.name,
            "username": player.username or "guest",
            "room_id": player.room_id,
            "room_name": room_name,
            "hp": player.hp,
            "max_hp": player.max_hp,
            "worn": worn_names,
            "effects": effects,
            "flags": active_flags,
        })
    return result


# ── config patch ──────────────────────────────────────────────────────────────

@admin_router.patch("/worlds/{world_id}/config")
async def patch_config(world_id: str, req: ConfigPatch, _=Depends(_require_admin)):
    from api.state import registry
    from gm.interpreter import GMInterpreter

    world = registry.get(world_id)
    if world is None:
        raise HTTPException(404, "World not found")

    if req.name:
        world.config.name = req.name
    if req.description is not None and req.description != "":
        world.config.description = req.description
    if req.max_players > 0:
        world.config.max_players = req.max_players
    if req.ollama_model:
        world.config.ollama_model = req.ollama_model
        world.gm = GMInterpreter(model=req.ollama_model)

    registry.save_config(world)
    return {"updated": world_id, "name": world.config.name}
