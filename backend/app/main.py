import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import reading_service
from .database import AsyncSessionLocal
from .routers import chat, exercises, readings, studio, terms, tracks, users

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Hand-made reading overrides are applied by the track's text module: load them once.
    try:
        async with AsyncSessionLocal() as db:
            await reading_service.load_all(db)
    except Exception as exc:   # e.g. migration 0007 not applied yet: computed readings only
        log.warning("Reading overrides not loaded: %s", exc)
    yield


app = FastAPI(title="LangLearn", lifespan=lifespan)
app.include_router(tracks.router)
app.include_router(users.router)
app.include_router(exercises.router)
app.include_router(chat.router)
app.include_router(studio.router)
app.include_router(terms.router)
app.include_router(readings.router)


@app.get("/health")
def health():
    return {"status": "ok"}
