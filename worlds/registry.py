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
                # load scripts (base + any expansion scripts)
                world.scripts.load(world_dir / "scripts")
                # seed the map from base seed.py
                seeder = world_dir / "seed.py"
                if seeder.exists():
                    _run_seeder(seeder, world)
                # apply manual.json (admin CRUD edits + AI expansion additions)
                manual_path = world_dir / "manual.json"
                if manual_path.exists():
                    try:
                        manual = json.loads(manual_path.read_text(encoding="utf-8"))
                        _apply_manual(world, manual)
                        log.debug("Applied manual.json for %s", config.id)
                    except Exception:
                        log.exception("Failed to apply manual.json for %s", config.id)
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


def _apply_manual(world: WorldInstance, data: dict):
    """Apply manual.json overrides: add/edit rooms, NPCs, items; delete entities."""
    from world.room import Room
    from entities.npc import NPC
    from entities.item import Item

    for room_id, rd in data.get("rooms", {}).items():
        action = rd.get("_action", "add")
        if action == "add" and room_id not in world.map._rooms:
            world.map.add_room(Room(
                id=room_id, name=rd.get("name", room_id),
                description=rd.get("description", ""),
                zone_id=rd.get("zone_id", "default"),
                x=rd.get("x", 0), y=rd.get("y", 0), z=rd.get("z", 0),
                exits=dict(rd.get("exits", {})),
                properties=dict(rd.get("properties", {})),
                creator=rd.get("creator"),
            ))
        elif action == "edit":
            r = world.map.get_room(room_id)
            if r:
                for k, v in rd.items():
                    if k != "_action" and hasattr(r, k):
                        setattr(r, k, v)

    for npc_id, nd in data.get("npcs", {}).items():
        action = nd.get("_action", "add")
        if action == "add" and npc_id not in world.npcs:
            world.npcs[npc_id] = NPC(
                id=npc_id, name=nd.get("name", npc_id),
                description=nd.get("description", ""),
                room_id=nd.get("room_id", ""),
                dialogue=list(nd.get("dialogue", [])),
                properties=dict(nd.get("properties", {})),
                creator=nd.get("creator"),
            )
        elif action == "edit":
            n = world.npcs.get(npc_id)
            if n:
                for k, v in nd.items():
                    if k != "_action" and hasattr(n, k):
                        setattr(n, k, v)

    for item_id, id_ in data.get("items", {}).items():
        action = id_.get("_action", "add")
        if action == "add" and item_id not in world.items:
            world.items[item_id] = Item(
                id=item_id, name=id_.get("name", item_id),
                description=id_.get("description", ""),
                item_type=id_.get("item_type", "misc"),
                properties=dict(id_.get("properties", {})),
                room_id=id_.get("room_id"),
                creator=id_.get("creator"),
            )
        elif action == "edit":
            i = world.items.get(item_id)
            if i:
                for k, v in id_.items():
                    if k != "_action" and hasattr(i, k):
                        setattr(i, k, v)

    for key in data.get("deleted", []):
        if ":" not in key:
            continue
        kind, eid = key.split(":", 1)
        if kind == "room":
            world.map.remove_room(eid)
        elif kind == "npc":
            world.npcs.pop(eid, None)
        elif kind == "item":
            world.items.pop(eid, None)

    _sync_entity_ids(world)


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
