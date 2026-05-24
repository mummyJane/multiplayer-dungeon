# Changelog

All changes are logged here with timestamps.

---

## [0.5.3] - 2026-05-24 (fix: world delete now removes files from disk)

### Fixed
- `worlds/registry.py` `remove()` now calls `shutil.rmtree(data/worlds/<id>/)` so deleted worlds don't reappear after a restart

---

## [0.5.2] - 2026-05-24 (stop and restart)

### Added
- `stop.py` — writes `.stop.flag`; `start.py` sees it within 0.5 s, terminates uvicorn cleanly, and exits. Falls back to `os.kill(SIGTERM)` if the server hasn't stopped after 8 s
- `restart.py` — sets `.restart.flag`, signals the current uvicorn process to exit; `start.py`'s poll loop detects the flag and immediately relaunches uvicorn without re-running pre-flight checks. Waits up to 10 s for the new PID and confirms
- `.server.pid`, `.restart.flag`, `.stop.flag` added to `.gitignore`

### Changed
- `start.py` — replaced `os.execv` with `subprocess.Popen` + a poll loop so the process stays alive across restarts. Writes `.server.pid` on each launch; clears it on exit. Checks `.stop.flag` and `.restart.flag` every 0.5 s

---

## [0.5.1] - 2026-05-24 (fix setup.py UnicodeDecodeError on Windows)

### Fixed
- `setup.py` `run()` helper now passes `encoding="utf-8", errors="replace"` to `subprocess.run` — prevents `UnicodeDecodeError` from cp1252 when capturing output that contains UTF-8 characters (e.g. Ollama's list output)
- `ollama pull` no longer captures output at all — Ollama's progress bar prints directly to the terminal, avoiding the reader-thread decode error entirely

---

## [0.5.0] - 2026-05-24 (player history + debug logging)

### Added
- `debug/player_log.py` — `PlayerDebugLogger`: per-player, per-world session log file written to `logs/<world_id>/<player>_<YYYYMMDD-HHMMSS>.log`. Enabled by `DEBUG_PLAYERS=1` in `.env`. Logs: `JOIN`, `LEAVE`, `MOVE`, `INPUT`, `SCRIPT` (name + event + context), `LLM_SEND` (model, prompt preview, char count), `LLM_RECV` (response preview, elapsed ms), `LLM_ERR`, `STATE` (hp, flags, inventory), `EVENT`, `ERROR`
- `entities/player.py` — `HistoryEntry` dataclass + `history: list[HistoryEntry]` on `Player`. `add_history(kind, text)` appends with timestamp, capped at 100 entries. `history_for_llm()` returns the last 20 as a plain-text block injected into the Ollama system prompt
- `.env.example` — `DEBUG_PLAYERS=0` documented

### Changed
- `gm/interpreter.py` — player input and GM response added to history on every turn; history block injected into Ollama system prompt; `llm_send` / `llm_recv` / `llm_error` debug calls added around every Ollama request; `state_snapshot` called before each LLM request
- `scripting/context.py` — `fire_rule` and `advance_workflow` call `dbg.script_trigger()` and `player.add_history()` for every handler that runs
- `worlds/instance.py` — `_debug_loggers: dict[player_id, PlayerDebugLogger]`; logger created on `join()`, closed on `leave()`; `get_debug_logger(player_id)` method for GM and scripts to retrieve it

---

## [0.4.0] - 2026-05-24 (paste/upload world spec)

### Added
- `POST /admin/worlds/upload` — accepts a multipart file upload (UTF-8 text, max 512 KB) and feeds it to the Claude world builder; same live-load flow as the paste path
- `web/css/admin.css` — admin-specific styles extracted from style.css
- Admin panel now has two tabs: "Paste spec / theme" (textarea) and "Upload file" (drag-and-drop or browse); both show a result preview table (world ID, name, rooms, NPCs, items)

### Changed
- `admin/builder.py` — switched to `AsyncAnthropic` client; updated system prompt to handle both short themes and long detailed spec documents; `max_tokens` raised to 8192; now generates `rules_script`, `routines_script`, AND `workflows_script`; `materialise_world` writes all three and also seeds `items` from the JSON
- `admin/routes.py` — `GenerateRequest` replaces `CreateWorldRequest` (field renamed `theme` → `text`); shared `_build_and_load()` helper used by both paste and upload endpoints; response now includes room/NPC/item counts
- `web/admin.html` — restructured around the two tabs; added result preview panel

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
