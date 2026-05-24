from __future__ import annotations
import logging
import random
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pathlib import Path

from auth.accounts import AccountManager
from storage.story_log import StoryLog

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
        story = StoryLog(username, world_id) if username else None

        await sessions.send(session_id, {
            "type": "welcome",
            "player_id": player.id,
            "name": player.name,
            "world": world.name,
        })
        await world.send_room_view(session_id, player)
        await world.send_status(session_id, player)

        initial_room_id = player.room_id
        room = world.map.get_room(player.room_id)
        await world.scripts.fire_rule("player_enter", player=player, room=room, world=world)

        # ── sync entity IDs if script teleported the player ───────────────────
        if player.room_id != initial_room_id:
            old_room = world.map.get_room(initial_room_id)
            if old_room:
                old_room.remove_entity(player.id)
            new_room = world.map.get_room(player.room_id)
            if new_room and player.id not in new_room.entity_ids:
                new_room.add_entity(player.id)

        # ── update client to reflect any script-side room/flag changes ────────
        await world.send_room_view(session_id, player)
        await world.send_status(session_id, player)

        # ── no-start-condition fallback ───────────────────────────────────────
        if not world.scripts._rules.get("player_enter"):
            log.warning("[%s] No player_enter handlers — %s placed in random room", world_id, player_name)
            room_ids = list(world.map._rooms.keys())
            if room_ids:
                new_room_id = random.choice(room_ids)
                if new_room_id != player.room_id:
                    old_room = world.map.get_room(player.room_id)
                    if old_room:
                        old_room.remove_entity(player.id)
                    player.room_id = new_room_id
                    new_room = world.map.get_room(new_room_id)
                    if new_room:
                        new_room.add_entity(player.id)
            await sessions.send(session_id, {
                "type": "message",
                "text": "[ No start condition defined for this world. ]",
            })
            await world.send_room_view(session_id, player)
            await world.send_status(session_id, player)

        # ── auto-look: print room description as text on arrival ─────────────
        look_text = await world.gm._look(player, world)
        await sessions.send(session_id, {"type": "message", "text": look_text})
        if story:
            _log_room(story, player, world)

        # ── main game loop ────────────────────────────────────────────────────
        while True:
            data = await ws.receive_json()
            text = str(data.get("text", "")).strip()
            if not text:
                continue
            if story:
                story.append("player_say", text=text)
            prior_room_id = player.room_id
            try:
                response = await world.gm.handle(player, text, world)
            except Exception as exc:
                log.exception("[%s] handle() error for %s: %s", world_id, player_name, exc)
                response = "Something went wrong. (server error)"
            if story:
                story.append("gm_reply", text=response)
            await sessions.send(session_id, {"type": "message", "text": response})
            await world.send_room_view(session_id, player)
            await world.send_status(session_id, player)
            # auto-look: when movement changes the room, print room description
            if player.room_id != prior_room_id:
                look_text = await world.gm._look(player, world)
                await sessions.send(session_id, {"type": "message", "text": look_text})
                if story:
                    _log_room(story, player, world)

    except WebSocketDisconnect:
        pass
    finally:
        world.leave(session_id)
        sessions.disconnect(session_id)


def _log_room(story: "StoryLog", player, world):
    room = world.map.get_room(player.room_id)
    if room is None:
        return
    npcs   = [world.npcs[e].name  for e in room.entity_ids if e in world.npcs]
    items  = [world.items[e].name for e in room.entity_ids if e in world.items]
    story.append(
        "enter_room",
        room_id=room.id,
        room_name=room.name,
        description=room.description,
        exits=list(room.exits.keys()),
        npcs=npcs,
        items=items,
    )
