# Changelog

All changes are logged here with timestamps.

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
