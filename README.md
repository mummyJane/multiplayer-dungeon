# Multiplayer Dungeon

A real-time multiplayer text adventure engine with an AI Game Master. Players explore persistent worlds via a browser; world admins build and expand content through an admin panel backed by Claude.

## Tech Stack

- **Backend:** Python 3.11+ · FastAPI · Uvicorn (ASGI)
- **Realtime:** WebSockets
- **Frontend:** Vanilla JS (no framework)
- **In-game GM:** Local LLM via [Ollama](https://ollama.ai) (`llama3` or any chat model)
- **World builder:** Claude API (Anthropic) — generates and expands worlds from a text spec

## Architecture

```
Browser ──WebSocket──► api/routes.py
                           │
               ┌───────────┼───────────────┐
               ▼           ▼               ▼
         ScriptEngine   OllamaGM      WorldInstance
         (rules /        (natural      (map, entities,
          routines /      language      sessions, tick
          workflows)      parser)       loop)
               │                         │
               └──────────► WorldRegistry (multi-world)
                                         │
                                  data/worlds/<id>/
                                  (seed.py + manual.json)
```

## Modules

| Module | Role |
|---|---|
| `engine/` | Adaptive tick loop |
| `world/` | Map, rooms (with floor `z`), zones |
| `entities/` | Players, NPCs, monsters, items (clothing slots, effects) |
| `combat/` | Script-driven combat resolution |
| `scripting/` | Event rules, tick routines, multi-step workflows |
| `gm/` | Ollama-backed Game Master — natural language input + live world creation |
| `network/` | WebSocket session manager |
| `api/` | FastAPI routes: game WS, player REST, admin REST |
| `auth/` | Account manager (PBKDF2 passwords, roles, profile, world states) |
| `admin/` | Claude-powered world builder and expander; admin HTTP routes |
| `storage/` | Story log (JSONL), data-repo git wrapper, backup manager |
| `worlds/` | World registry, instance lifecycle, `manual.json` overlay |
| `web/` | Browser UI: game client, player dashboard, admin panel |

## Accounts and roles

| Role | Can do |
|---|---|
| `player` | Play in any world |
| `world_admin` | Play + edit/expand their assigned worlds via the admin panel |
| `admin` | Full rights — create/delete worlds, manage all accounts, set roles |

Passwords are hashed with PBKDF2-HMAC-SHA256. Accounts persist player position, inventory, worn items, flags, and per-world notes across sessions.

## Worlds

Each world lives under `data/worlds/<id>/`:

```
data/worlds/<id>/
  config.json      — name, description, Ollama model, max players
  seed.py          — Python script that populates rooms, NPCs, items on load
  manual.json      — CRUD edits and AI expansion additions (overlaid over seed.py)
  scripts/
    rules/         — event handlers  (player_enter, player_say, …)
    routines/      — tick-driven behaviour
    workflows/     — multi-step NPC sequences
```

Worlds can be:
- **Generated** from a text spec (via the admin "Create World with Claude" section)
- **Expanded** room-by-room with Claude (via the world editor "Expand with AI" tab)
- **Edited** manually in the world editor (CRUD for rooms, NPCs, items; inline script editor)

## First-time setup

```bash
python setup.py
```

- Checks Python 3.11+
- Installs all pip dependencies into `.venv/`
- Creates `.env` interactively (admin secret, API keys, Ollama model, host/port)
- Creates `data/` and `backups/` directories and initialises data-tracking git repos
- Verifies Ollama is installed and offers to pull the configured model

## Starting the server

```bash
python start.py          # normal mode
DEV=1 python start.py    # auto-reload (development)
```

Pre-flight on every start: packages, `.env`, Ollama (auto-starts if installed but not running), at least one world, Anthropic API key (warns if missing — only needed for world building/expansion).

```bash
python restart.py        # hot-reload without dropping player connections
python stop.py           # clean shutdown
```

## URLs

| URL | Who | Description |
|---|---|---|
| `http://localhost:8000` | Players | World select → auth overlay → game room |
| `http://localhost:8000/player` | Players | Dashboard: profile, world notes, story log |
| `http://localhost:8000/admin` | Admins | Create worlds, edit content, manage accounts |

## Environment variables (`.env`)

| Variable | Purpose |
|---|---|
| `ADMIN_SECRET` | API key for full admin access |
| `ANTHROPIC_API_KEY` | Required for world generation and expansion |
| `OLLAMA_MODEL` | Ollama model for the in-game GM (default `llama3`) |
| `OLLAMA_HOST` | Ollama base URL (default `http://localhost:11434`) |
| `HOST` / `PORT` | Bind address (default `0.0.0.0:8000`) |
| `DEBUG_PLAYERS` | `1` to write per-player debug logs to `logs/` |

## Change log

See [CHANGELOG.md](CHANGELOG.md)
