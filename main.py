import logging
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from api.routes import router
from api.state import game_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

app = FastAPI(title="Dungeon")

# serve static assets
WEB_DIR = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

app.include_router(router)


@app.on_event("startup")
async def startup():
    game_state.world.seed_starter_world()
    game_state.start_loop()
    logging.getLogger(__name__).info("World seeded. Game loop started.")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
