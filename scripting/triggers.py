"""Script trigger engine — maps event names to handler callables."""
from __future__ import annotations
import logging
from typing import Callable, Awaitable, Any

log = logging.getLogger(__name__)

Handler = Callable[..., Awaitable[None]]


class TriggerEngine:
    def __init__(self):
        self._handlers: dict[str, list[Handler]] = {}

    def on(self, event: str):
        """Decorator: @triggers.on('player.enter')"""
        def decorator(fn: Handler) -> Handler:
            self._handlers.setdefault(event, []).append(fn)
            return fn
        return decorator

    async def fire(self, event: str, **kwargs: Any):
        for handler in self._handlers.get(event, []):
            try:
                await handler(**kwargs)
            except Exception:
                log.exception("Trigger handler error for event '%s'", event)
