from __future__ import annotations
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path

log = logging.getLogger(__name__)
router = APIRouter()

_WEB_DIR = Path(__file__).parent.parent / "web"


@router.get("/", response_class=HTMLResponse)
async def index():
    return (_WEB_DIR / "index.html").read_text(encoding="utf-8")


@router.get("/health")
async def health():
    from api.state import registry
    return {
        "status": "ok",
        "worlds": [{"id": w.id, "name": w.name, "players": w.player_count} for w in registry.all()],
    }


@router.get("/worlds")
async def list_worlds():
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


@router.websocket("/ws/{world_id}")
async def ws_endpoint(ws: WebSocket, world_id: str):
    from api.state import registry

    world = registry.get(world_id)
    if world is None:
        await ws.close(code=4004, reason="World not found")
        return

    sessions = world.sessions
    session_id = sessions.new_session_id()
    await sessions.connect(session_id, ws)

    try:
        await sessions.send(session_id, {"type": "prompt", "text": "Enter your name:"})
        data = await ws.receive_json()
        player_name = str(data.get("text", "")).strip()[:24] or "Wanderer"

        player = world.join(session_id, player_name)

        await sessions.send(session_id, {
            "type": "welcome",
            "player_id": player.id,
            "name": player.name,
            "world": world.name,
        })
        await world.send_room_view(session_id, player)

        # fire player_enter rule
        room = world.map.get_room(player.room_id)
        await world.scripts.fire_rule("player_enter", player=player, room=room, world=world)

        while True:
            data = await ws.receive_json()
            text = str(data.get("text", "")).strip()
            if not text:
                continue
            response = await world.gm.handle(player, text, world)
            await sessions.send(session_id, {"type": "message", "text": response})
            await world.send_room_view(session_id, player)

    except WebSocketDisconnect:
        pass
    finally:
        world.leave(session_id)
        sessions.disconnect(session_id)
