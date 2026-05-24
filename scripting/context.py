"""Per-world script loader and dispatcher.

Script layout under data/worlds/<id>/scripts/:
  rules/      *.py  — event handlers  (functions: on_<event>(player, room, world))
  routines/   *.py  — tick actions    (function: run(world, tick_count))
  workflows/  *.py  — multi-step seq  (function: on_progress(player, step, world))
"""
from __future__ import annotations
import importlib.util
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Awaitable

if TYPE_CHECKING:
    from worlds.instance import WorldInstance

log = logging.getLogger(__name__)

Handler = Callable[..., Awaitable[None]]


class ScriptContext:
    def __init__(self, world_id: str):
        self.world_id = world_id
        # event name -> list of handler callables
        self._rules: dict[str, list[Handler]] = {}
        # list of (module, run callable) for routines
        self._routines: list[tuple[str, Handler]] = []
        # workflow name -> on_progress callable
        self._workflows: dict[str, Handler] = {}

    def load(self, scripts_dir: Path):
        """Load all scripts from the world's scripts directory."""
        for category in ("rules", "routines", "workflows"):
            d = scripts_dir / category
            if not d.exists():
                continue
            for script_file in sorted(d.glob("*.py")):
                self._load_script(category, script_file)

    def _load_script(self, category: str, path: Path):
        name = f"{self.world_id}.{category}.{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if category == "rules":
                # register any on_<event> functions
                for attr in dir(mod):
                    if attr.startswith("on_"):
                        event = attr[3:]  # strip "on_"
                        fn = getattr(mod, attr)
                        if callable(fn):
                            self._rules.setdefault(event, []).append(fn)
                            log.debug("[%s] rule registered: %s -> %s", self.world_id, event, name)

            elif category == "routines":
                if hasattr(mod, "run") and callable(mod.run):
                    self._routines.append((name, mod.run))
                    log.debug("[%s] routine registered: %s", self.world_id, name)

            elif category == "workflows":
                if hasattr(mod, "on_progress") and callable(mod.on_progress):
                    self._workflows[path.stem] = mod.on_progress
                    log.debug("[%s] workflow registered: %s", self.world_id, path.stem)

        except Exception:
            log.exception("[%s] Failed to load script: %s", self.world_id, path)

    # --- dispatch ---

    async def fire_rule(self, event: str, **kwargs: Any):
        for handler in self._rules.get(event, []):
            try:
                await handler(**kwargs)
            except Exception:
                log.exception("[%s] Rule handler error for event '%s'", self.world_id, event)

    async def run_routines(self, world: "WorldInstance"):
        tick = world._loop.tick_count
        for name, run_fn in self._routines:
            try:
                await run_fn(world=world, tick_count=tick)
            except Exception:
                log.exception("[%s] Routine error: %s", self.world_id, name)

    async def advance_workflow(self, workflow: str, **kwargs: Any):
        fn = self._workflows.get(workflow)
        if fn is None:
            log.warning("[%s] Unknown workflow: %s", self.world_id, workflow)
            return
        try:
            await fn(**kwargs)
        except Exception:
            log.exception("[%s] Workflow error: %s", self.world_id, workflow)
