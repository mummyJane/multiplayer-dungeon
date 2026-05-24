from __future__ import annotations
import uuid
import logging
from fastapi import WebSocket

log = logging.getLogger(__name__)


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, WebSocket] = {}
        self._player_session: dict[str, str] = {}   # player_id -> session_id
        self._session_player: dict[str, str] = {}   # session_id -> player_id

    def new_session_id(self) -> str:
        return str(uuid.uuid4())

    async def connect(self, session_id: str, ws: WebSocket):
        await ws.accept()
        self._sessions[session_id] = ws
        log.info("Session connected: %s", session_id)

    def disconnect(self, session_id: str):
        self._sessions.pop(session_id, None)
        player_id = self._session_player.pop(session_id, None)
        if player_id:
            self._player_session.pop(player_id, None)
        log.info("Session disconnected: %s", session_id)

    def bind_player(self, session_id: str, player_id: str):
        self._player_session[player_id] = session_id
        self._session_player[session_id] = player_id

    def player_for_session(self, session_id: str) -> str | None:
        return self._session_player.get(session_id)

    def session_for_player(self, player_id: str) -> str | None:
        return self._player_session.get(player_id)

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    async def send(self, session_id: str, message: dict):
        ws = self._sessions.get(session_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                log.warning("Failed to send to session %s", session_id)

    async def broadcast(self, message: dict, exclude: str | None = None):
        for sid, ws in list(self._sessions.items()):
            if sid == exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                log.warning("Broadcast failed for session %s", sid)
