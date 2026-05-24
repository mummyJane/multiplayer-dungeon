from __future__ import annotations
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pathlib import Path

log = logging.getLogger(__name__)
router = APIRouter()

_WEB_DIR = Path(__file__).parent.parent / "web"


@router.get("/", response_class=HTMLResponse)
async def index():
    return (_WEB_DIR / "index.html").read_text(encoding="utf-8")


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    from .state import game_state   # late import to avoid circular
    sessions = game_state.sessions
    gm = game_state.gm

    session_id = sessions.new_session_id()
    await sessions.connect(session_id, ws)

    try:
        # ask for player name
        await sessions.send(session_id, {"type": "prompt", "text": "Enter your name:"})
        data = await ws.receive_json()
        player_name = str(data.get("text", "Unknown"))[:24].strip() or "Unknown"

        player = game_state.join(session_id, player_name)
        await sessions.send(session_id, {
            "type": "welcome",
            "player_id": player.id,
            "name": player.name,
        })
        await game_state.send_room_view(session_id, player)

        while True:
            data = await ws.receive_json()
            text = str(data.get("text", "")).strip()
            if text:
                response = await gm.handle(player, text, game_state)
                await sessions.send(session_id, {"type": "message", "text": response})
                await game_state.send_room_view(session_id, player)

    except WebSocketDisconnect:
        pass
    finally:
        game_state.leave(session_id)
        sessions.disconnect(session_id)
