"""Admin HTTP routes — world management and Claude API world builder."""
from __future__ import annotations
import json
import os
import secrets
import logging
from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pathlib import Path
from typing import Optional

_DATA_ROOT = Path(__file__).parent.parent / "data" / "worlds"

log = logging.getLogger(__name__)
admin_router = APIRouter(prefix="/admin")

_WEB_DIR = Path(__file__).parent.parent / "web"
_ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "changeme")
_MAX_UPLOAD_BYTES = 512 * 1024  # 512 KB

# in-memory admin session tokens: token → {username, role, managed_worlds}
_admin_tokens: dict[str, dict] = {}


# ── auth helpers ──────────────────────────────────────────────────────────────

def _resolve_auth(x_admin_key: str = "", authorization: str = "") -> dict:
    """Return auth info dict or raise 403."""
    if x_admin_key == _ADMIN_SECRET:
        return {"role": "admin", "username": "__key__", "managed_worlds": []}
    if authorization.startswith("Bearer "):
        info = _admin_tokens.get(authorization[7:])
        if info:
            return info
    raise HTTPException(status_code=403, detail="Not authenticated")


def _require_admin(
    x_admin_key: str = Header(default=""),
    authorization: str = Header(default=""),
) -> dict:
    auth = _resolve_auth(x_admin_key, authorization)
    if auth["role"] != "admin":
        raise HTTPException(403, "Full admin access required")
    return auth


def _require_any_admin(
    x_admin_key: str = Header(default=""),
    authorization: str = Header(default=""),
) -> dict:
    return _resolve_auth(x_admin_key, authorization)


def _check_world_access(world_id: str, auth: dict):
    """Raise 403 if auth doesn't cover this world."""
    if auth["role"] == "admin":
        return
    if auth["role"] == "world_admin" and world_id in auth.get("managed_worlds", []):
        return
    raise HTTPException(403, "No access to this world")


# ── models ────────────────────────────────────────────────────────────────────

class AdminAuthRequest(BaseModel):
    username: str
    password: str


class GenerateRequest(BaseModel):
    text: str


class ExpandRequest(BaseModel):
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


class RoomCreate(BaseModel):
    id: str
    name: str
    description: str = ""
    zone_id: str = "default"
    x: int = 0
    y: int = 0
    z: int = 0
    exits: dict = {}
    properties: dict = {}


class RoomPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    zone_id: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    z: Optional[int] = None
    exits: Optional[dict] = None
    properties: Optional[dict] = None


class NpcCreate(BaseModel):
    id: str
    name: str
    description: str = ""
    room_id: str = ""
    dialogue: list = []
    properties: dict = {}


class NpcPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    room_id: Optional[str] = None
    dialogue: Optional[list] = None
    properties: Optional[dict] = None


class ItemCreate(BaseModel):
    id: str
    name: str
    description: str = ""
    item_type: str = "misc"
    room_id: Optional[str] = None
    properties: dict = {}


class ItemPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    item_type: Optional[str] = None
    room_id: Optional[str] = None
    properties: Optional[dict] = None


class RoleSet(BaseModel):
    role: str
    managed_worlds: list = []


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


@admin_router.post("/auth")
async def admin_auth(req: AdminAuthRequest):
    """Login with a player account that has world_admin or admin role."""
    from auth.accounts import AccountManager
    accounts = AccountManager()
    ok, err = accounts.login(req.username.strip().lower(), req.password)
    if not ok:
        raise HTTPException(401, err)
    acc = accounts.get(req.username.strip().lower())
    if acc is None or acc.role not in ("world_admin", "admin"):
        raise HTTPException(403, "Account does not have admin access")
    token = secrets.token_hex(32)
    _admin_tokens[token] = {
        "username": acc.username,
        "role": acc.role,
        "managed_worlds": list(acc.managed_worlds),
    }
    return {"token": token, "role": acc.role, "managed_worlds": acc.managed_worlds}


@admin_router.post("/logout")
async def admin_logout(authorization: str = Header(default="")):
    if authorization.startswith("Bearer "):
        _admin_tokens.pop(authorization[7:], None)
    return {"ok": True}


@admin_router.get("/worlds")
async def list_worlds(auth: dict = Depends(_require_any_admin)):
    from api.state import registry
    worlds = registry.all()
    # world_admin sees only their managed worlds
    if auth["role"] == "world_admin":
        worlds = [w for w in worlds if w.id in auth.get("managed_worlds", [])]
    return [
        {
            "id": w.id,
            "name": w.name,
            "description": w.config.description,
            "players": w.player_count,
            "max_players": w.config.max_players,
        }
        for w in worlds
    ]


@admin_router.post("/worlds/generate")
async def generate_world(req: GenerateRequest, auth: dict = Depends(_require_admin)):
    """Generate a world from pasted text (theme or full spec)."""
    if not req.text.strip():
        raise HTTPException(400, "Text is empty")
    return await _build_and_load(req.text)


@admin_router.post("/worlds/upload")
async def upload_world_spec(
    file: UploadFile = File(...),
    auth: dict = Depends(_require_admin),
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
async def create_world_manual(req: WorldConfigRequest, auth: dict = Depends(_require_admin)):
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
async def delete_world(world_id: str, auth: dict = Depends(_require_admin)):
    from api.state import registry
    registry.remove(world_id)
    return {"removed": world_id}


@admin_router.post("/worlds/{world_id}/reload-scripts")
async def reload_scripts(world_id: str,
                         x_admin_key: str = Header(default=""),
                         authorization: str = Header(default="")):
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
async def world_detail(world_id: str, auth: dict = Depends(_require_any_admin)):
    from api.state import registry
    _check_world_access(world_id, auth)
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
            "creator":      r.creator,
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
            "creator":      n.creator,
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
            "creator":      i.creator,
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
async def get_scripts(world_id: str, auth: dict = Depends(_require_any_admin)):
    """Return content of generated.py for each script category."""
    scripts_dir = _DATA_ROOT / world_id / "scripts"
    result = {}
    for cat in ("rules", "routines", "workflows"):
        path = scripts_dir / cat / "generated.py"
        result[cat] = path.read_text(encoding="utf-8") if path.exists() else ""
    return result


@admin_router.put("/worlds/{world_id}/scripts")
async def save_scripts(world_id: str, req: ScriptsSave, auth: dict = Depends(_require_any_admin)):
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
async def world_players(world_id: str, auth: dict = Depends(_require_any_admin)):
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
async def patch_config(world_id: str, req: ConfigPatch, auth: dict = Depends(_require_any_admin)):
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


# ── manual.json helpers ───────────────────────────────────────────────────────

def _load_manual(world_id: str) -> dict:
    path = _DATA_ROOT / world_id / "manual.json"
    if not path.exists():
        return {"rooms": {}, "npcs": {}, "items": {}, "deleted": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_manual(world_id: str, data: dict):
    path = _DATA_ROOT / world_id / "manual.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _manual_apply_live(world_id: str, world):
    """Re-apply all manual.json changes to the live world instance."""
    from worlds.registry import _apply_manual
    manual = _load_manual(world_id)
    _apply_manual(world, manual)


# ── CRUD: rooms ───────────────────────────────────────────────────────────────

@admin_router.post("/worlds/{world_id}/rooms")
async def create_room(world_id: str, req: RoomCreate,
                      auth: dict = Depends(_require_any_admin)):
    from api.state import registry
    from world.room import Room
    _check_world_access(world_id, auth)
    world = registry.get(world_id)
    if world is None:
        raise HTTPException(404, "World not found")
    if world.map.get_room(req.id):
        raise HTTPException(409, f"Room '{req.id}' already exists")
    room = Room(id=req.id, name=req.name, description=req.description,
                zone_id=req.zone_id, x=req.x, y=req.y, z=req.z,
                exits=req.exits, properties=req.properties, creator=None)
    world.map.add_room(room)
    manual = _load_manual(world_id)
    manual["rooms"][req.id] = {"_action": "add", **req.model_dump(), "creator": None}
    _save_manual(world_id, manual)
    return {"created": req.id}


@admin_router.patch("/worlds/{world_id}/rooms/{room_id}")
async def patch_room(world_id: str, room_id: str, req: RoomPatch,
                     auth: dict = Depends(_require_any_admin)):
    from api.state import registry
    _check_world_access(world_id, auth)
    world = registry.get(world_id)
    if world is None:
        raise HTTPException(404, "World not found")
    room = world.map.get_room(room_id)
    if room is None:
        raise HTTPException(404, f"Room '{room_id}' not found")
    patch = {k: v for k, v in req.model_dump().items() if v is not None}
    for k, v in patch.items():
        setattr(room, k, v)
    manual = _load_manual(world_id)
    existing = manual["rooms"].get(room_id, {})
    if existing.get("_action") == "add":
        existing.update(patch)
    else:
        existing = {"_action": "edit", **patch}
    manual["rooms"][room_id] = existing
    _save_manual(world_id, manual)
    return {"updated": room_id}


@admin_router.delete("/worlds/{world_id}/rooms/{room_id}")
async def delete_room(world_id: str, room_id: str,
                      auth: dict = Depends(_require_any_admin)):
    from api.state import registry
    _check_world_access(world_id, auth)
    world = registry.get(world_id)
    if world is None:
        raise HTTPException(404, "World not found")
    world.map.remove_room(room_id)
    manual = _load_manual(world_id)
    manual["rooms"].pop(room_id, None)
    deleted_key = f"room:{room_id}"
    if deleted_key not in manual["deleted"]:
        manual["deleted"].append(deleted_key)
    _save_manual(world_id, manual)
    return {"deleted": room_id}


# ── CRUD: NPCs ────────────────────────────────────────────────────────────────

@admin_router.post("/worlds/{world_id}/npcs")
async def create_npc(world_id: str, req: NpcCreate,
                     auth: dict = Depends(_require_any_admin)):
    from api.state import registry
    from entities.npc import NPC
    _check_world_access(world_id, auth)
    world = registry.get(world_id)
    if world is None:
        raise HTTPException(404, "World not found")
    if req.id in world.npcs:
        raise HTTPException(409, f"NPC '{req.id}' already exists")
    npc = NPC(id=req.id, name=req.name, description=req.description,
              room_id=req.room_id, dialogue=req.dialogue, properties=req.properties)
    world.npcs[npc.id] = npc
    if npc.room_id:
        room = world.map.get_room(npc.room_id)
        if room and npc.id not in room.entity_ids:
            room.add_entity(npc.id)
    manual = _load_manual(world_id)
    manual["npcs"][req.id] = {"_action": "add", **req.model_dump()}
    _save_manual(world_id, manual)
    return {"created": req.id}


@admin_router.patch("/worlds/{world_id}/npcs/{npc_id}")
async def patch_npc(world_id: str, npc_id: str, req: NpcPatch,
                    auth: dict = Depends(_require_any_admin)):
    from api.state import registry
    _check_world_access(world_id, auth)
    world = registry.get(world_id)
    if world is None:
        raise HTTPException(404, "World not found")
    npc = world.npcs.get(npc_id)
    if npc is None:
        raise HTTPException(404, f"NPC '{npc_id}' not found")
    patch = {k: v for k, v in req.model_dump().items() if v is not None}
    for k, v in patch.items():
        setattr(npc, k, v)
    manual = _load_manual(world_id)
    existing = manual["npcs"].get(npc_id, {})
    if existing.get("_action") == "add":
        existing.update(patch)
    else:
        existing = {"_action": "edit", **patch}
    manual["npcs"][npc_id] = existing
    _save_manual(world_id, manual)
    return {"updated": npc_id}


@admin_router.delete("/worlds/{world_id}/npcs/{npc_id}")
async def delete_npc(world_id: str, npc_id: str,
                     auth: dict = Depends(_require_any_admin)):
    from api.state import registry
    _check_world_access(world_id, auth)
    world = registry.get(world_id)
    if world is None:
        raise HTTPException(404, "World not found")
    npc = world.npcs.pop(npc_id, None)
    if npc and npc.room_id:
        room = world.map.get_room(npc.room_id)
        if room:
            room.remove_entity(npc_id)
    manual = _load_manual(world_id)
    manual["npcs"].pop(npc_id, None)
    deleted_key = f"npc:{npc_id}"
    if deleted_key not in manual["deleted"]:
        manual["deleted"].append(deleted_key)
    _save_manual(world_id, manual)
    return {"deleted": npc_id}


# ── CRUD: items ───────────────────────────────────────────────────────────────

@admin_router.post("/worlds/{world_id}/items")
async def create_item(world_id: str, req: ItemCreate,
                      auth: dict = Depends(_require_any_admin)):
    from api.state import registry
    from entities.item import Item
    _check_world_access(world_id, auth)
    world = registry.get(world_id)
    if world is None:
        raise HTTPException(404, "World not found")
    if req.id in world.items:
        raise HTTPException(409, f"Item '{req.id}' already exists")
    item = Item(id=req.id, name=req.name, description=req.description,
                item_type=req.item_type, room_id=req.room_id, properties=req.properties)
    world.items[item.id] = item
    if item.room_id:
        room = world.map.get_room(item.room_id)
        if room and item.id not in room.entity_ids:
            room.add_entity(item.id)
    manual = _load_manual(world_id)
    manual["items"][req.id] = {"_action": "add", **req.model_dump()}
    _save_manual(world_id, manual)
    return {"created": req.id}


@admin_router.patch("/worlds/{world_id}/items/{item_id}")
async def patch_item(world_id: str, item_id: str, req: ItemPatch,
                     auth: dict = Depends(_require_any_admin)):
    from api.state import registry
    _check_world_access(world_id, auth)
    world = registry.get(world_id)
    if world is None:
        raise HTTPException(404, "World not found")
    item = world.items.get(item_id)
    if item is None:
        raise HTTPException(404, f"Item '{item_id}' not found")
    patch = {k: v for k, v in req.model_dump().items() if v is not None}
    for k, v in patch.items():
        setattr(item, k, v)
    manual = _load_manual(world_id)
    existing = manual["items"].get(item_id, {})
    if existing.get("_action") == "add":
        existing.update(patch)
    else:
        existing = {"_action": "edit", **patch}
    manual["items"][item_id] = existing
    _save_manual(world_id, manual)
    return {"updated": item_id}


@admin_router.delete("/worlds/{world_id}/items/{item_id}")
async def delete_item(world_id: str, item_id: str,
                      auth: dict = Depends(_require_any_admin)):
    from api.state import registry
    _check_world_access(world_id, auth)
    world = registry.get(world_id)
    if world is None:
        raise HTTPException(404, "World not found")
    item = world.items.pop(item_id, None)
    if item and item.room_id:
        room = world.map.get_room(item.room_id)
        if room:
            room.remove_entity(item_id)
    manual = _load_manual(world_id)
    manual["items"].pop(item_id, None)
    deleted_key = f"item:{item_id}"
    if deleted_key not in manual["deleted"]:
        manual["deleted"].append(deleted_key)
    _save_manual(world_id, manual)
    return {"deleted": item_id}


# ── world expansion ───────────────────────────────────────────────────────────

@admin_router.post("/worlds/{world_id}/expand")
async def expand_world_endpoint(world_id: str, req: ExpandRequest,
                                auth: dict = Depends(_require_any_admin)):
    from api.state import registry
    from admin.builder import expand_world, materialise_expansion
    from worlds.registry import _apply_manual
    import traceback

    _check_world_access(world_id, auth)
    world = registry.get(world_id)
    if world is None:
        raise HTTPException(404, "World not found")
    if not req.text.strip():
        raise HTTPException(400, "Expansion spec is empty")

    build_log: list[str] = []

    try:
        data = await expand_world(world, req.text, build_log)
    except Exception as exc:
        build_log.append(f"ABORT  Claude call failed: {exc}")
        raise HTTPException(500, detail={"error": str(exc), "build_log": build_log})

    try:
        world_dir, script_errors = materialise_expansion(world_id, data)
        for se in script_errors:
            build_log.append(f"WARN   Script syntax error: {se}")
    except Exception as exc:
        build_log.append(f"ABORT  materialise_expansion failed: {exc}")
        raise HTTPException(500, detail={"error": str(exc), "build_log": build_log})

    # live-apply to running world
    try:
        from admin.builder import _load_manual as bld_load_manual
        manual = bld_load_manual(world_id)
        _apply_manual(world, manual)
        build_log.append("LIVE   Changes applied to running world")
    except Exception as exc:
        build_log.append(f"WARN   Live apply failed: {exc}")

    # reload expansion scripts
    try:
        world.scripts.load(world_dir / "scripts")
        build_log.append("LOAD   Expansion scripts loaded")
    except Exception as exc:
        build_log.append(f"WARN   Script reload error: {exc}")

    return {
        "world_id": world_id,
        "rooms": len(data.get("rooms", [])),
        "npcs": len(data.get("npcs", [])),
        "items": len(data.get("items", [])),
        "build_log": build_log,
    }


# ── accounts management (full admin) ─────────────────────────────────────────

@admin_router.get("/accounts")
async def list_accounts(auth: dict = Depends(_require_admin)):
    from auth.accounts import AccountManager
    return AccountManager().list_accounts()


@admin_router.patch("/accounts/{username}/role")
async def set_account_role(username: str, req: RoleSet,
                           auth: dict = Depends(_require_admin)):
    from auth.accounts import AccountManager
    ok, err = AccountManager().set_role(username, req.role, req.managed_worlds)
    if not ok:
        raise HTTPException(400, err)
    # refresh cached token if they're currently logged in
    for token, info in _admin_tokens.items():
        if info["username"] == username:
            info["role"] = req.role
            info["managed_worlds"] = list(req.managed_worlds)
    return {"updated": username, "role": req.role}
