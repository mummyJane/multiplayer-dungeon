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

## Running

```bash
pip install -r requirements.txt
python main.py
```

Open `http://localhost:8000` in your browser.

Requires [Ollama](https://ollama.ai) running locally for the Game Master.

## Change Log

See [CHANGELOG.md](CHANGELOG.md)
