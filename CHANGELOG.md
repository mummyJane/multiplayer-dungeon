# Changelog

All changes are logged here with timestamps.

---

## [0.3.1] - 2026-05-24 (local venv)

### Changed
- `setup.py` now creates `.venv/` inside the project directory and installs all dependencies into it (no global pip installs)
- `start.py` detects whether it is running inside `.venv/`; if not, it transparently re-execs itself using `.venv/Scripts/python.exe` (Windows) or `.venv/bin/python` (Unix) so the user never needs to activate manually
- `.venv/` was already in `.gitignore` — confirmed correct

---

## [0.3.0] - 2026-05-24 (setup and start scripts)

### Added
- `setup.py` — one-time system setup: checks Python version, installs dependencies, creates `.env` interactively, creates data directories, verifies Ollama installation, offers to pull the configured model
- `start.py` — pre-flight launch script: loads `.env`, checks all packages, warns on default admin secret, verifies worlds exist, checks Anthropic API key, starts Ollama automatically if installed but not running, then exec's uvicorn. Handles SIGINT/SIGTERM cleanly
- `.env.example` — template for environment variables (ADMIN_SECRET, ANTHROPIC_API_KEY, OLLAMA settings, HOST/PORT)
- `logs/` directory added to `.gitignore`
- README updated with setup/start instructions

---

## [0.2.0] - 2026-05-24 (multi-world architecture)

### Added
- `worlds/` module: `WorldInstance` (isolated world with its own map, entities, scripts, sessions, loop) and `WorldRegistry` (manages multiple live worlds, loads from `data/worlds/` on startup)
- `scripting/context.py`: per-world Python script loader — discovers and registers `rules/*.py` (event handlers), `routines/*.py` (tick-driven), `workflows/*.py` (multi-step sequences)
- `admin/` module: FastAPI admin routes (`/admin`) with Claude API world builder — describe a theme, Claude generates rooms/NPCs/monsters/scripts and live-loads the world; manual world creation and script hot-reload also supported
- `worlds/thornwall/`: example world with seed map (6 rooms, 2 zones), 2 NPCs, 1 monster, a rule (deep forest warning), a routine (wolf patrol), and a workflow (missing Aldric quest)
- World selection screen in frontend — players pick a world before connecting
- Admin panel (`/admin`) with Claude-generate, manual create, reload-scripts, and delete
- `world/map.py`: `set_entry_room()` and `default_entry_room()` helpers
- `anthropic` added to `requirements.txt` for admin world builder

### Changed
- `api/state.py` replaced single `GameState` with `WorldRegistry`
- `api/routes.py` WS endpoint now scoped to `/ws/{world_id}`; added `GET /worlds` for world list
- `gm/interpreter.py` updated to accept `WorldInstance` instead of old `GameState`
- `web/index.html` + `web/js/main.js` updated for world selection flow
- Frontend shows world name, NPCs, and monsters in room view

---

## [0.1.0] - 2026-05-24 (initial scaffold)

### Added
- Project structure: engine, world, entities, combat, scripting, gm, network, api, web modules
- FastAPI application skeleton with WebSocket support
- Adaptive tick engine (speeds up with more players)
- Tile-based world map with zone support
- Player, NPC, monster, and item entity models
- Script-driven event trigger system
- Ollama-backed Game Master module for natural language input
- HTMX + vanilla JS frontend skeleton
- WebSocket session manager
- CHANGELOG.md, README.md, .gitignore, requirements.txt
