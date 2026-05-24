"""Per-world script loader and dispatcher.

Script layout under data/worlds/<id>/scripts/:
  rules/      *.py  — event handlers  (functions: on_<event>(player, room, world))
  routines/   *.py  — tick actions    (function: run(world, tick_count))
  workflows/  *.py  — multi-step seq  (function: on_progress(player, step, world))
"""
from __future__ import annotations
import importlib.util
import logging
import sys
import types
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Awaitable

if TYPE_CHECKING:
    from worlds.instance import WorldInstance

log = logging.getLogger(__name__)

Handler = Callable[..., Awaitable[None]]


class ScriptContext:
    def __init__(self, world_id: str):
        self.world_id = world_id
        self._rules:     dict[str, list[Handler]] = {}
        self._routines:  list[tuple[str, Handler]] = []
        self._workflows: dict[str, Handler] = {}
        # bare_key ("rules.generated") → loaded module, for cross-script imports
        self._loaded_mods: dict[str, Any] = {}

    def load(self, scripts_dir: Path):
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

            # Temporarily inject already-loaded scripts under their bare names
            # (e.g. "rules.generated") so that cross-script imports like
            #   from rules.generated import find_free_room
            # resolve correctly.  Cleaned up immediately after exec.
            injected: list[str] = []
            for bare_key, loaded_mod in self._loaded_mods.items():
                if bare_key not in sys.modules:
                    sys.modules[bare_key] = loaded_mod
                    injected.append(bare_key)
                # Python also needs the parent package name present
                pkg = bare_key.rsplit(".", 1)[0] if "." in bare_key else None
                if pkg and pkg not in sys.modules:
                    sys.modules[pkg] = types.ModuleType(pkg)
                    injected.append(pkg)

            try:
                spec.loader.exec_module(mod)
            finally:
                for k in injected:
                    sys.modules.pop(k, None)

            # Keep this module so later scripts can import from it
            self._loaded_mods[f"{category}.{path.stem}"] = mod

            if category == "rules":
                for attr in dir(mod):
                    if attr.startswith("on_"):
                        event = attr[3:]
                        fn = getattr(mod, attr)
                        if callable(fn):
                            self._rules.setdefault(event, []).append(fn)
                            log.debug("[%s] rule registered: %s → %s", self.world_id, event, name)

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

    # ── dispatch ──────────────────────────────────────────────────────────────

    async def fire_rule(self, event: str, **kwargs: Any):
        handlers = self._rules.get(event, [])
        if not handlers:
            return

        # pull debug logger if player is in kwargs
        player = kwargs.get("player")
        world  = kwargs.get("world")
        dbg = world.get_debug_logger(player.id) if (world and player) else None

        for handler in handlers:
            script_name = getattr(handler, "__module__", "?")
            ctx_summary = (
                f"room={kwargs['room'].id}" if "room" in kwargs else ""
            )
            if dbg:
                dbg.script_trigger(script_name, event, ctx_summary)
            if player:
                player.add_history("script", f"[{event}] {script_name}")

            try:
                await handler(**kwargs)
            except Exception:
                if dbg:
                    dbg.error(f"Rule handler '{script_name}' raised an exception")
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

        player = kwargs.get("player")
        world  = kwargs.get("world")
        dbg = world.get_debug_logger(player.id) if (world and player) else None
        step = kwargs.get("step", "?")

        if dbg:
            dbg.script_trigger(f"workflow:{workflow}", "on_progress", f"step={step}")
        if player:
            player.add_history("script", f"[workflow:{workflow}] step={step}")

        try:
            await fn(**kwargs)
        except Exception:
            if dbg:
                dbg.error(f"Workflow '{workflow}' raised an exception at step={step}")
            log.exception("[%s] Workflow error: %s", self.world_id, workflow)
