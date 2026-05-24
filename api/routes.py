from __future__ import annotations
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pathlib import Path

from auth.accounts import AccountManager

log = logging.getLogger(__name__)
router = APIRouter()

_WEB_DIR = Path(__file__).parent.parent / "web"
_accounts = AccountManager()


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

    username = ""
    player_name = ""

    try:
        # ── auth handshake ────────────────────────────────────────────────────
        await sessions.send(session_id, {"type": "auth_prompt"})

        data = await ws.receive_json()
        action   = str(data.get("action", "")).strip()   # "login" | "register" | "guest"
        uname    = str(data.get("username", "")).strip()[:32].lower()
        password = str(data.get("password", "")).strip()

        if action == "register":
            ok, err = _accounts.register(uname, password)
            if not ok:
                await sessions.send(session_id, {"type": "auth_error", "text": err})
                return
            username = uname
            await sessions.send(session_id, {"type": "auth_ok", "text": "Account created!"})

        elif action == "login":
            ok, err = _accounts.login(uname, password)
            if not ok:
                await sessions.send(session_id, {"type": "auth_error", "text": err})
                return
            username = uname
            await sessions.send(session_id, {"type": "auth_ok", "text": f"Welcome back, {uname}!"})

        else:
            # guest — no account required
            await sessions.send(session_id, {"type": "auth_ok", "text": "Joining as guest."})

        # ── name prompt ───────────────────────────────────────────────────────
        display_name = username or ""
        if not display_name:
            await sessions.send(session_id, {"type": "prompt", "text": "Enter your name:"})
            data = await ws.receive_json()
            display_name = str(data.get("text", "")).strip()[:24] or "Wanderer"
        player_name = display_name

        # ── join world ────────────────────────────────────────────────────────
        player = world.join(session_id, player_name, username=username)

        await sessions.send(session_id, {
            "type": "welcome",
            "player_id": player.id,
            "name": player.name,
            "world": world.name,
        })
        await world.send_room_view(session_id, player)

        room = world.map.get_room(player.room_id)
        await world.scripts.fire_rule("player_enter", player=player, room=room, world=world)

        # ── main game loop ────────────────────────────────────────────────────
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
