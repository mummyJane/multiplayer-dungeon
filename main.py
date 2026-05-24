import logging
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from api.routes import router
from admin.routes import admin_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

app = FastAPI(title="Dungeon")

WEB_DIR = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

app.include_router(router)
app.include_router(admin_router)


@app.on_event("startup")
async def startup():
    from api.state import registry
    registry.load_from_disk()
    log = logging.getLogger(__name__)
    worlds = registry.all()
    log.info("Loaded %d world(s): %s", len(worlds), [w.id for w in worlds])


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
