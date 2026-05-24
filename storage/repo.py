"""Local-only git repository wrapper for data dirs (worlds and players).

These repos are never pushed to GitHub — they exist solely for local
versioned history and tagged checkpoints.
"""
from __future__ import annotations
import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


class DataRepo:
    """Manages a local git repo rooted at `path`."""

    def __init__(self, path: Path):
        self.path = path
        path.mkdir(parents=True, exist_ok=True)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def init(self):
        """Initialise repo if not already a git repo."""
        if (self.path / ".git").exists():
            return
        self._run("git init")
        self._run('git config user.name "dungeon-data"')
        self._run('git config user.email "dungeon@localhost"')
        # write a .gitkeep so the initial commit has something
        (self.path / ".gitkeep").touch()
        self._run("git add .gitkeep")
        self._run('git commit -m "init data repo"')
        log.info("Initialised data repo at %s", self.path)

    # ── operations ────────────────────────────────────────────────────────────

    def commit_all(self, message: str):
        """Stage everything and commit (no-op if nothing changed)."""
        self._run("git add -A")
        # --allow-empty would hide bugs; check status first
        result = self._run("git status --porcelain", capture=True)
        if not result.strip():
            return  # nothing to commit
        self._run(f'git commit -m "{_esc(message)}"')
        log.debug("Data repo commit: %s", message)

    def tag(self, name: str, message: str = ""):
        """Create an annotated tag at HEAD."""
        msg = message or name
        self._run(f'git tag -a "{_esc(name)}" -m "{_esc(msg)}"')
        log.info("Data repo tag: %s @ %s", name, self.path)

    def tag_exists(self, name: str) -> bool:
        result = self._run(f'git tag -l "{_esc(name)}"', capture=True)
        return bool(result.strip())

    # ── internal ─────────────────────────────────────────────────────────────

    def _run(self, cmd: str, capture: bool = False) -> str:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(self.path),
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0 and not capture:
            log.warning("Data repo command failed: %s\n%s", cmd,
                        (result.stderr or "")[:400])
        return result.stdout if capture else ""


def _esc(s: str) -> str:
    """Minimal escaping for git CLI strings (avoids shell injection)."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
