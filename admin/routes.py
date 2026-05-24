"""Admin HTTP routes — world management and Claude API world builder."""
from __future__ import annotations
import os
import logging
from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pathlib import Path

log = logging.getLogger(__name__)
admin_router = APIRouter(prefix="/admin")

_WEB_DIR = Path(__file__).parent.parent / "web"
_ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "changeme")


def _require_admin(x_admin_key: str = Header(default="")):
    if x_admin_key != _ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin key")


# --- models ---

class CreateWorldRequest(BaseModel):
    theme: str


class WorldConfigRequest(BaseModel):
    id: str
    name: str
    description: str = ""
    max_players: int = 50
    ollama_model: str = "llama3"


# --- routes ---

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
async def generate_world(req: CreateWorldRequest, _=Depends(_require_admin)):
    """Use Claude API to generate a new world from a theme description."""
    from admin.builder import build_world, materialise_world
    from api.state import registry
    from worlds.registry import _run_seeder

    data = await build_world(req.theme)
    world_dir = materialise_world(data)

    # live-load the new world
    from worlds.instance import WorldConfig
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
    seeder = world_dir / "seed.py"
    if seeder.exists():
        _run_seeder(seeder, world)
    world.start_loop()

    return {"world_id": config.id, "name": config.name}


@admin_router.post("/worlds/manual")
async def create_world_manual(req: WorldConfigRequest, _=Depends(_require_admin)):
    """Create a blank world manually (admin builds rooms/scripts by hand)."""
    from api.state import registry
    from worlds.instance import WorldConfig
    from pathlib import Path
    import json

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
    from pathlib import Path
    world = registry.get(world_id)
    if world is None:
        raise HTTPException(404, "World not found")
    scripts_dir = Path(__file__).parent.parent / "data" / "worlds" / world_id / "scripts"
    from scripting.context import ScriptContext
    world.scripts = ScriptContext(world_id)
    world.scripts.load(scripts_dir)
    return {"reloaded": world_id}
