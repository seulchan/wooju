"""FastAPI application composition and Brain lifecycle.

The entry point owns startup/shutdown concerns: it builds the in-memory catalog,
starts the optional read-only watcher, and wires the HTTP router. Route
handlers live in :mod:`app.api.routes`; domain projections remain framework-agnostic.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from brain_core.index import BrainIndex

from .api.dependencies import get_brain_path
from .api.routes import api_router
from .config import build_health, watch_enabled
from .watcher import watch_and_refresh

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wooju")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the initial catalog and manage the optional watcher task."""
    brain_path = get_brain_path()
    health = build_health(brain_path)
    index = BrainIndex()
    watcher_task: asyncio.Task[None] | None = None

    if health.brain_valid and brain_path is not None:
        index.scan(brain_path)
        logger.info("Brain ready at %s", health.brain_path)
        if watch_enabled():
            watcher_task = asyncio.create_task(
                watch_and_refresh(index, brain_path), name="wooju-brain-watcher"
            )
        else:
            logger.info("File watching disabled (WOOJU_DISABLE_FILE_WATCH set)")
    else:
        logger.warning("Brain not ready: %s", health.message)

    app.state.index = index
    app.state.watcher_task = watcher_task
    try:
        yield
    finally:
        if watcher_task is not None:
            watcher_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher_task


app = FastAPI(
    title="Wooju API",
    description="Local-first API for the Wooju app. Reads the Brain; never edits it directly.",
    version="0.2.0",
    lifespan=lifespan,
)

# The Vite dev server proxies /api to this backend. These origins also support
# direct browser access in development and the POST used for UI-only state.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(api_router)
