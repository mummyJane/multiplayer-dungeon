"""Zip-archive backups for worlds and players.

Archives are written to backups/worlds/ and backups/players/.
The backups/ directory is gitignored from the main repo.
"""
from __future__ import annotations
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent
_BACKUP_ROOT = _ROOT / "backups"


class BackupManager:

    @staticmethod
    def backup_world(world_id: str) -> Path:
        """Zip data/worlds/<world_id>/ → backups/worlds/<world_id>_<ts>.zip"""
        src = _ROOT / "data" / "worlds" / world_id
        if not src.exists():
            raise FileNotFoundError(f"World directory not found: {src}")
        return _archive(src, _BACKUP_ROOT / "worlds", world_id)

    @staticmethod
    def backup_player(username: str) -> Path:
        """Zip data/players/<username>/ → backups/players/<username>_<ts>.zip"""
        src = _ROOT / "data" / "players" / username
        if not src.exists():
            raise FileNotFoundError(f"Player directory not found: {src}")
        return _archive(src, _BACKUP_ROOT / "players", username)

    @staticmethod
    def backup_all_worlds() -> list[Path]:
        worlds_dir = _ROOT / "data" / "worlds"
        if not worlds_dir.exists():
            return []
        results = []
        for d in worlds_dir.iterdir():
            if d.is_dir():
                try:
                    results.append(BackupManager.backup_world(d.name))
                except Exception:
                    log.exception("Failed to backup world: %s", d.name)
        return results

    @staticmethod
    def backup_all_players() -> list[Path]:
        players_dir = _ROOT / "data" / "players"
        if not players_dir.exists():
            return []
        results = []
        for d in players_dir.iterdir():
            if d.is_dir():
                try:
                    results.append(BackupManager.backup_player(d.name))
                except Exception:
                    log.exception("Failed to backup player: %s", d.name)
        return results


def _archive(src: Path, dest_dir: Path, name: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive_base = dest_dir / f"{name}_{ts}"
    out = shutil.make_archive(str(archive_base), "zip", root_dir=src.parent, base_dir=src.name)
    log.info("Backup created: %s", out)
    return Path(out)
