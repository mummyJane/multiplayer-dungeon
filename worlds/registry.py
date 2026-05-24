"""Registry of all live world instances."""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Optional

from .instance import WorldInstance, WorldConfig
from storage.repo import DataRepo

log = logging.getLogger(__name__)

_DATA_ROOT = Path(__file__).parent.parent / "data" / "worlds"
_worlds_repo: Optional[DataRepo] = None


def _get_worlds_repo() -> DataRepo:
    global _worlds_repo
    if _worlds_repo is None:
        _worlds_repo = DataRepo(_DATA_ROOT)
        _worlds_repo.init()
    return _worlds_repo


class WorldRegistry:
    def __init__(self):
        self._worlds: dict[str, WorldInstance] = {}

    # --- lifecycle ---

    def create(self, config: WorldConfig) -> WorldInstance:
        if config.id in self._worlds:
            raise ValueError(f"World '{config.id}' already exists")
        world = WorldInstance(config)
        self._worlds[config.id] = world
        log.info("World created: %s (%s)", config.name, config.id)
        return world

    def _commit_and_tag_world(self, world_id: str, action: str):
        """Commit worlds data repo and tag after a world is created or deleted."""
        try:
            repo = _get_worlds_repo()
            repo.commit_all(f"{action} world: {world_id}")
            tag_name = f"world-{action}-{world_id}"
            if not repo.tag_exists(tag_name):
                repo.tag(tag_name, f"World {action}: {world_id}")
        except Exception:
            log.exception("Failed to commit worlds repo after %s %s", action, world_id)

    def get(self, world_id: str) -> Optional[WorldInstance]:
        return self._worlds.get(world_id)

    def all(self) -> list[WorldInstance]:
        return list(self._worlds.values())

    def remove(self, world_id: str):
        world = self._worlds.pop(world_id, None)
        if world:
            world._loop.stop()

        world_dir = _DATA_ROOT / world_id
        if world_dir.exists():
            import shutil
            shutil.rmtree(world_dir)
            log.info("World deleted from disk: %s", world_dir)
            self._commit_and_tag_world(world_id, "deleted")

        if world:
            log.info("World removed: %s", world_id)

    # --- persistence: load worlds from data/worlds/<id>/config.json ---

    def load_from_disk(self):
        if not _DATA_ROOT.exists():
            return
        for world_dir in _DATA_ROOT.iterdir():
            if not world_dir.is_dir():
                continue
            cfg_path = world_dir / "config.json"
            if not cfg_path.exists():
                continue
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                config = WorldConfig(
                    id=cfg["id"],
                    name=cfg["name"],
                    description=cfg.get("description", ""),
                    max_players=cfg.get("max_players", 50),
                    ollama_model=cfg.get("ollama_model", "llama3"),
                )
                world = self.create(config)
                # load scripts
                world.scripts.load(world_dir / "scripts")
                # seed the map if a seeder script exists
                seeder = world_dir / "seed.py"
                if seeder.exists():
                    _run_seeder(seeder, world)
                world.start_loop()
                log.info("World loaded from disk: %s", config.id)
            except Exception:
                log.exception("Failed to load world from %s", world_dir)

    def save_config(self, world: WorldInstance):
        world_dir = _DATA_ROOT / world.id
        world_dir.mkdir(parents=True, exist_ok=True)
        cfg = {
            "id": world.config.id,
            "name": world.config.name,
            "description": world.config.description,
            "max_players": world.config.max_players,
            "ollama_model": world.config.ollama_model,
        }
        (world_dir / "config.json").write_text(
            json.dumps(cfg, indent=2), encoding="utf-8"
        )
        self._commit_and_tag_world(world.id, "created")


def _run_seeder(path: Path, world: WorldInstance):
    import importlib.util
    spec = importlib.util.spec_from_file_location("_seeder", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if hasattr(mod, "seed"):
        mod.seed(world)
    _sync_entity_ids(world)


def _sync_entity_ids(world: WorldInstance):
    """Populate room entity_ids from NPC and item room_id fields set during seeding."""
    for npc in world.npcs.values():
        if npc.room_id:
            room = world.map.get_room(npc.room_id)
            if room and npc.id not in room.entity_ids:
                room.add_entity(npc.id)
    for item in world.items.values():
        if item.room_id:
            room = world.map.get_room(item.room_id)
            if room and item.id not in room.entity_ids:
                room.add_entity(item.id)
