"""Admin HTTP routes — world management and Claude API world builder."""
from __future__ import annotations
import os
import logging
from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pathlib import Path

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


# ── shared world-creation helper ──────────────────────────────────────────────

async def _build_and_load(spec_text: str):
    """Build from spec_text, materialise to disk, live-load, and return summary."""
    from admin.builder import build_world, materialise_world
    from api.state import registry
    from worlds.instance import WorldConfig
    from worlds.registry import _run_seeder

    data = await build_world(spec_text)
    world_dir = materialise_world(data)

    cfg_data = data["config"]
    config = WorldConfig(
        id=cfg_data["id"],
        name=cfg_data["name"],
        description=cfg_data.get("description", ""),
        max_players=cfg_data.get("max_players", 50),
        ollama_model=cfg_data.get("ollama_model", "llama3"),
    )
    world = registry.create(config)
    world.scripts.load(world_dir / "scripts")
    if (world_dir / "seed.py").exists():
        _run_seeder(world_dir / "seed.py", world)
    world.start_loop()

    rooms  = len(data.get("rooms", []))
    npcs   = len(data.get("npcs", []))
    items  = len(data.get("items", []))
    return {
        "world_id": config.id,
        "name": config.name,
        "rooms": rooms,
        "npcs": npcs,
        "items": items,
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
    scripts_dir = Path(__file__).parent.parent / "data" / "worlds" / world_id / "scripts"
    world.scripts = ScriptContext(world_id)
    world.scripts.load(scripts_dir)
    return {"reloaded": world_id}
