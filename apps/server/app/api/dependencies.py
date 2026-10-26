"""FastAPI dependencies shared by the HTTP routes."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request

from brain_core.index import BrainIndex

from ..config import resolve_brain_path


def get_brain_path() -> Path | None:
    """FastAPI dependency returning the resolved Brain path."""
    return resolve_brain_path()


BrainPathDep = Annotated[Path | None, Depends(get_brain_path)]


def get_index(request: Request) -> BrainIndex:
    """Return the in-memory catalog owned by the application lifespan."""
    return request.app.state.index


IndexDep = Annotated[BrainIndex, Depends(get_index)]
