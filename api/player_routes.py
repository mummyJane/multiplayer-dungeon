"""Player-facing HTTP API for the dashboard.

Auth: POST /player/auth → bearer token stored in memory.
All other endpoints require Authorization: Bearer <token>.
"""
from __future__ import annotations
import secrets
import logging
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pathlib import Path
from typing import Optional

from auth.accounts import AccountManager

log = logging.getLogger(__name__)
player_router = APIRouter(prefix="/player")

_accounts = AccountManager()
_WEB_DIR = Path(__file__).parent.parent / "web"

# in-memory token → username map (lost on restart, dashboard re-login required)
_tokens: dict[str, str] = {}


# ── models ────────────────────────────────────────────────────────────────────

class AuthRequest(BaseModel):
    username: str
    password: str


class ProfilePatch(BaseModel):
    email: str = ""
    sex: str = ""
    real_age: str = ""
    description: str = ""


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


class WorldContextPatch(BaseModel):
    context: str


# ── routes ────────────────────────────────────────────────────────────────────

@player_router.get("/", response_class=HTMLResponse)
async def player_dashboard():
    return (_WEB_DIR / "player.html").read_text(encoding="utf-8")


@player_router.post("/auth")
async def player_auth(req: AuthRequest):
    """Login and return a bearer token for dashboard API calls."""
    ok, err = _accounts.login(req.username.strip().lower(), req.password)
    if not ok:
        raise HTTPException(status_code=401, detail=err)
    token = secrets.token_hex(32)
    _tokens[token] = req.username.strip().lower()
    return {"token": token, "username": req.username.strip().lower()}


@player_router.post("/logout")
async def player_logout(authorization: str = Header(default="")):
    if authorization.startswith("Bearer "):
        _tokens.pop(authorization[7:], None)
    return {"ok": True}


from fastapi import Depends


def _auth(authorization: str = Header(default="")) -> str:
    if authorization.startswith("Bearer "):
        token = authorization[7:]
        u = _tokens.get(token)
        if u:
            return u
    raise HTTPException(status_code=401, detail="Not authenticated")


@player_router.get("/profile")
async def get_profile(username: str = Depends(_auth)):
    acc = _accounts.get(username)
    if acc is None:
        raise HTTPException(404, "Account not found")
    return {
        "username":    acc.username,
        "email":       acc.email,
        "sex":         acc.sex,
        "real_age":    acc.real_age,
        "description": acc.description,
        "created_at":  acc.created_at,
        "last_login":  acc.last_login,
    }


@player_router.patch("/profile")
async def patch_profile(req: ProfilePatch, username: str = Depends(_auth)):
    fields = {k: v for k, v in req.model_dump().items() if v != ""}
    ok, err = _accounts.update_profile(username, **fields)
    if not ok:
        raise HTTPException(400, err)
    return {"updated": True}


@player_router.post("/change-password")
async def change_password(req: PasswordChange, username: str = Depends(_auth)):
    ok, err = _accounts.change_password(username, req.old_password, req.new_password)
    if not ok:
        raise HTTPException(400, err)
    return {"updated": True}


@player_router.get("/worlds")
async def player_worlds(username: str = Depends(_auth)):
    """Return all worlds the player has state saved for."""
    from api.state import registry
    acc = _accounts.get(username)
    if acc is None:
        raise HTTPException(404)
    result = []
    for world_id, state in acc.world_states.items():
        world = registry.get(world_id)
        result.append({
            "world_id":   world_id,
            "world_name": world.name if world else world_id,
            "online":     world is not None,
            "last_room":  state.get("room_id", ""),
            "hp":         state.get("hp", 100),
            "context":    acc.world_context.get(world_id, ""),
        })
    return result


@player_router.get("/story/{world_id}")
async def player_story(world_id: str, n: int = 200, username: str = Depends(_auth)):
    """Return last n story log entries for this player in world_id."""
    from storage.story_log import StoryLog
    log_obj = StoryLog(username, world_id)
    return {"entries": log_obj.tail(n)}


@player_router.patch("/worlds/{world_id}/context")
async def set_world_context(world_id: str, req: WorldContextPatch,
                            username: str = Depends(_auth)):
    _accounts.set_world_context(username, world_id, req.context)
    return {"updated": True}
