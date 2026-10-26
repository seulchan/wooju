"""FastAPI application composition and lifecycle.

The :class:`~app.engine.Engine` owns the open Brain, its in-memory index, the
file watcher, and the ingest queue. Read routes live in :mod:`app.api.routes`;
routes that change things live in :mod:`app.api.actions`.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.actions import actions_router
from .api.routes import api_router
from .engine import Engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wooju")


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = Engine()
    app.state.engine = engine
    app.state.index = engine.index
    await engine.start()
    if engine.brain is None:
        logger.warning("No Brain folder chosen yet; waiting for first-run setup.")
    try:
        yield
    finally:
        await engine.stop()


app = FastAPI(
    title="Wooju API",
    description="Local-first API for the Wooju app. Agents propose; the user approves.",
    version="0.3.0",
    lifespan=lifespan,
)

# The Vite dev server proxies /api to this backend. These origins also support
# direct browser access in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(api_router)
app.include_router(actions_router)


def web_dist() -> Path:
    """The built UI (``npm run web:build``); override with ``WOOJU_WEB_DIST``."""
    override = os.environ.get("WOOJU_WEB_DIST", "").strip()
    return Path(override) if override else Path(__file__).resolve().parents[2] / "web" / "dist"


# One process serves both the API and the UI, so the desktop app starts one server.
if web_dist().is_dir():
    app.mount("/", StaticFiles(directory=web_dist(), html=True), name="web")
