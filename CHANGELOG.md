# Changelog

All changes are logged here with timestamps.

---

## [0.6.2] - 2026-05-24 (admin build log — debug send/receive/load)

### Added
- Build log panel in admin UI: after every Generate or Upload attempt, a colour-coded log appears showing each step: `SEND` (spec length + preview), `RECV` (raw response length + preview + stop_reason), `PARSE` (JSON success or exact error position), `WRITE`, `LOAD`, `SEED`, `START`, and `WARN`/`ABORT`/`ERROR` on failures. Log is also printed to the server console via `log.info`/`log.warning`.

### Changed
- `admin/builder.py` `build_world()` now accepts a `build_log` list and appends step entries; raises with a clear message if `ANTHROPIC_API_KEY` is missing
- `admin/routes.py` `_build_and_load()` now wraps each step (Claude call, materialise, registry create, scripts, seed) in individual try/except blocks; always returns `build_log` in the response body; on failure returns the log inside the `detail` object so the UI can still show it
- `web/js/admin.js` `showBuildLog()` renders each log line with a colour matching its verb (green=OK, cyan=load, yellow=warn, red=error); called on both success and failure
- `web/admin.html` — `#build-log-section` / `#build-log` panel added below the preview table
- `web/css/admin.css` — build log pre-box styles added

---

## [0.6.1] - 2026-05-24 (multi-floor building support for world builder)

### Added
- `world/room.py` — `z: int = 0` floor-level coordinate on `Room` (negative = basement, 0 = ground, positive = upper floors). Exits already support `up`/`down`; `z` makes the floor explicit for scripts and the GM.

### Changed
- `admin/builder.py` system prompt rewritten to handle complex building specs:
  - Full map-layout rules: hallway-per-direction constraint, `z` encoding, `up`/`down` stair exits, numbered room sets (e.g. "4 punishment nurseries" → 4 separate rooms)
  - `room.properties` and `npc.properties` now documented and used by the builder for metadata (floor name, room type, capacity, NPC role, shift times)
  - `player.flags` guidance added for implementing state-machine rules (punishment tags, levels, timed constraints)
  - Routine shift-scheduling pattern shown (read `npc.properties["shift"]`, broadcast to a room)
- `admin/builder.py` `materialise_world()` now writes `z=`, `room.properties=`, `npc.properties=`, and `item.properties=` into the generated `seed.py`
- `admin/builder.py` `max_tokens` raised from 8192 → 16384 to accommodate large multi-room worlds

---

## [0.6.0] - 2026-05-24 (player accounts, data repos, backups)

### Added
- `auth/accounts.py` — `AccountManager`: register/login with PBKDF2-HMAC-SHA256 password hashing (stdlib only, no extra deps). Accounts stored as JSON in `data/players/<username>/account.json`. `save_world_state` / `load_world_state` persists per-world player position, hp, inventory, and flags
- `storage/repo.py` — `DataRepo`: thin wrapper around a local git repo. `init()` creates repo + initial commit; `commit_all(msg)` stages everything and commits; `tag(name, msg)` creates annotated tags. Used for `data/worlds/` and `data/players/` — never pushed to GitHub
- `storage/backup.py` — `BackupManager`: `backup_world(id)` / `backup_player(username)` / `backup_all_*()` create timestamped zip archives under `backups/worlds/` and `backups/players/`
- Frontend login/register/guest overlay — three-tab auth screen appears after world selection; accounts restore previous position and state; guests play without an account

### Changed
- `entities/player.py` — added `username: str`, `flags: dict`, `to_state()` serialiser, `from_state()` class method for save/restore
- `worlds/instance.py` — `join(session_id, name, username="")` now accepts an account username; restores saved world state on join; `leave()` persists state for logged-in players
- `worlds/registry.py` — `save_config()` and `remove()` now commit+tag the worlds data repo after each world create/delete
- `api/routes.py` — WebSocket handshake now has an auth step (`auth_prompt` → login/register/guest → `auth_ok`/`auth_error`) before the name prompt
- `web/index.html` + `web/js/main.js` — auth overlay with Login/Register/Guest tabs; JS handles `auth_prompt`, `auth_ok`, `auth_error` messages
- `web/css/style.css` — tab bar + auth tab styles added
- `.gitignore` — `data/`, `backups/`, `logs/`, `.server.pid`, `.restart.flag`, `.stop.flag`, `.claude/` all excluded from main repo
- `setup.py` — `create_data_dirs()` now also creates `data/players/` and `backups/`; `_init_data_repos()` initialises git repos inside `data/worlds/` and `data/players/`

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
