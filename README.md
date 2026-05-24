# Multiplayer Dungeon

A real-time multiplayer dungeon/world game with an LLM Game Master.

## Tech Stack

- **Backend:** Python + FastAPI (modular)
- **Realtime:** WebSockets
- **Frontend:** HTMX + vanilla JS
- **Game Master:** Local LLM via Ollama
- **Map:** Tile/grid-based world with buildings and dungeons

## Architecture

```
Player (browser) → WebSocket → API
                                ↓
                    LLM GM ←→ Script Engine
                                ↓
                          World State
                                ↓
                    Broadcast → All clients
```

## Modules

| Module | Role |
|---|---|
| `engine/` | Tick loop, adaptive time scaling |
| `world/` | Map grid, zones, rooms, buildings |
| `entities/` | Players, NPCs, monsters, items |
| `combat/` | Script-driven combat resolution |
| `scripting/` | Event triggers, item/NPC behaviour |
| `gm/` | LLM Game Master — input parsing & world creation |
| `network/` | WebSocket session management |
| `api/` | FastAPI routes + WebSocket endpoints |
| `web/` | HTMX frontend |

## First-time setup

```bash
python setup.py
```

This will:
- Check your Python version (3.11+ required)
- Install all dependencies
- Create a `.env` config file (interactive)
- Verify Ollama is installed and offer to pull the default model
- Check that at least one world exists

## Starting the server

```bash
python start.py
```

Pre-flight checks on every start:
- All packages present
- `.env` loaded
- Ollama running (starts it automatically if installed but not running)
- At least one world exists
- Anthropic API key set (warns if missing — only needed for world generation)

Then launches uvicorn. Use `DEV=1 python start.py` for auto-reload mode.

| URL | Description |
|---|---|
| `http://localhost:8000` | Player UI (world select → play) |
| `http://localhost:8000/admin` | Admin panel (create/manage worlds) |

Requires [Ollama](https://ollama.ai) for the in-game Game Master.

## Change Log

See [CHANGELOG.md](CHANGELOG.md)
