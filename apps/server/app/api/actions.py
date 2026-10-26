"""Routes that change things: first-run setup, adding files, approvals, undo.

Every write goes through :class:`app.engine.Engine`. Messages in ``detail`` are
written for the person using the app, not for developers.
"""

from __future__ import annotations

import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel

from brain_core import history
from brain_core.changes import Proposal, ProposalError
from wooju_agents.llm import (
    ANTHROPIC_DEFAULT_MODEL,
    OPENAI_DEFAULT_MODEL,
    LLMError,
    OllamaProvider,
    recommended_ollama_model,
)

from .. import settings as app_settings
from ..engine import Engine, SetupError

actions_router = APIRouter(prefix="/api")


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


EngineDep = Annotated[Engine, Depends(get_engine)]


def _fail(message: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail=message)


# --------------------------------------------------------------------- setup


class AiStatus(BaseModel):
    provider: str
    model: str
    ready: bool
    pulling: bool = False
    ollama_running: bool | None = None
    model_downloaded: bool | None = None
    has_key: bool | None = None
    message: str | None = None


class SetupStatus(BaseModel):
    brain_path: str | None
    brain_ready: bool
    language: str
    ai: AiStatus


def _ai_status() -> AiStatus:
    ai = app_settings.load().ai
    if ai.provider == "ollama":
        model = ai.model or recommended_ollama_model()
        status = OllamaProvider(model, host=ai.ollama_host).status()
        if not status["running"]:
            message = "Ollama가 설치되지 않았거나 꺼져 있어요."
        elif not status["model_ready"]:
            message = f"AI 모델({model})을 받아야 해요."
        else:
            message = None
        return AiStatus(
            provider="ollama",
            model=model,
            ready=status["running"] and status["model_ready"],
            ollama_running=status["running"],
            model_downloaded=status["model_ready"],
            message=message,
        )
    default = OPENAI_DEFAULT_MODEL if ai.provider == "openai" else ANTHROPIC_DEFAULT_MODEL
    has_key = app_settings.get_api_key(ai.provider) is not None
    return AiStatus(
        provider=ai.provider,
        model=ai.model or default,
        ready=has_key,
        has_key=has_key,
        message=None if has_key else "API 키를 입력해 주세요.",
    )


@actions_router.get("/setup", tags=["setup"], response_model=SetupStatus)
def setup_status(engine: EngineDep) -> SetupStatus:
    ai = _ai_status()
    pull = engine.pull_state
    if pull["model"] == ai.model:
        ai.pulling = pull["state"] == "pulling"
        if pull["state"] == "failed" and not ai.ready:
            ai.message = pull["message"]
    return SetupStatus(
        brain_path=str(engine.brain) if engine.brain else None,
        brain_ready=engine.brain is not None,
        language=engine.language(),
        ai=ai,
    )


@actions_router.post("/setup/ai/pull", tags=["setup"])
async def pull_model(engine: EngineDep) -> dict[str, Any]:
    """Download the recommended local model through Ollama (no terminal needed)."""
    await engine.pull_model()
    return dict(engine.pull_state)


class ChooseBrain(BaseModel):
    path: str


@actions_router.post("/setup/brain", tags=["setup"])
async def choose_brain(body: ChooseBrain, engine: EngineDep) -> dict[str, Any]:
    if not body.path.strip():
        raise _fail("폴더를 골라 주세요.")
    try:
        created = await engine.choose_brain(Path(body.path.strip()))
    except SetupError as exc:
        raise _fail(str(exc)) from exc
    return {"brain_path": str(engine.brain), "created": created}


class ChooseAi(BaseModel):
    provider: Literal["ollama", "openai", "anthropic"]
    model: str | None = None
    api_key: str | None = None


@actions_router.post("/setup/ai", tags=["setup"], response_model=AiStatus)
async def choose_ai(body: ChooseAi, engine: EngineDep) -> AiStatus:
    if body.provider != "ollama" and body.api_key:
        try:
            app_settings.set_api_key(body.provider, body.api_key.strip())
        except app_settings.KeyStoreError as exc:
            raise _fail(
                "키를 안전하게 저장하지 못했어요. Mac의 키체인 접근을 허용해 주세요."
            ) from exc
    current = app_settings.load()
    current.ai.provider = body.provider
    current.ai.model = body.model
    app_settings.save(current)
    status = _ai_status()
    if body.provider != "ollama" and status.ready:
        try:  # connection test with a tiny request
            engine.provider().generate_json(
                "Reply with JSON.",
                "Say ok.",
                {"type": "object", "properties": {"ok": {"type": "boolean"}}},
            )
        except LLMError as exc:
            status.ready, status.message = False, exc.user_message
    return status


# Pages the app may open in the user's browser. Anything else is refused, so a
# compromised page cannot use this to launch arbitrary URLs or programs.
OPENABLE_URLS = {
    "https://ollama.com/download",
    "https://console.anthropic.com/settings/keys",
    "https://platform.openai.com/api-keys",
}


class OpenUrl(BaseModel):
    url: str


@actions_router.post("/open", tags=["setup"])
def open_url(body: OpenUrl) -> dict[str, bool]:
    """Open an allowed page in the default browser (the desktop window cannot)."""
    if body.url not in OPENABLE_URLS:
        raise _fail("이 주소는 열 수 없어요.", 403)
    if sys.platform == "darwin":
        subprocess.run(["open", body.url], check=False, timeout=10)
    else:
        webbrowser.open(body.url)
    return {"opened": True}


# --------------------------------------------------------------------- inbox


@actions_router.post("/inbox", tags=["inbox"])
async def add_files(files: list[UploadFile], engine: EngineDep) -> dict[str, Any]:
    added, refused = [], []
    for upload in files:
        try:
            rel = await engine.receive(upload.filename or "file", await upload.read())
        except SetupError as exc:
            refused.append({"file": upload.filename, "message": str(exc)})
            continue
        job = await engine.enqueue(rel)
        added.append(job.to_dict())
    if not added and refused and engine.brain is None:
        raise _fail(refused[0]["message"])
    return {"added": added, "refused": refused}


@actions_router.post("/inbox/process", tags=["inbox"])
async def process_inbox(engine: EngineDep) -> dict[str, Any]:
    try:
        jobs = await engine.enqueue_inbox()
    except SetupError as exc:
        raise _fail(str(exc)) from exc
    return {"queued": [j.to_dict() for j in jobs]}


@actions_router.get("/jobs", tags=["inbox"])
def jobs(engine: EngineDep) -> dict[str, Any]:
    items = sorted(engine.jobs.values(), key=lambda j: j.created_at, reverse=True)
    return {"items": [j.to_dict() for j in items[:100]]}


# ----------------------------------------------------------------- proposals


class ChangeView(BaseModel):
    op: str
    path: str


class ProposalView(BaseModel):
    id: str
    title: str
    summary: str
    approval: str
    status: str
    agent: str
    origin: str | None
    created_at: str
    decided_at: str | None
    commit: str | None
    error: str | None
    changes: list[ChangeView]
    preview: str | None  # the main note, shown only when the card is expanded


def _view(p: Proposal) -> ProposalView:
    first = next((c for c in p.changes if c.op == "write" and c.content), None)
    return ProposalView(
        **p.model_dump(exclude={"changes"}),
        changes=[ChangeView(op=c.op, path=c.path) for c in p.changes],
        preview=first.content[:6000] if first else None,
    )


@actions_router.get("/proposals", tags=["proposals"])
def list_proposals(
    engine: EngineDep, status: Literal["pending", "applied", "rejected", "failed"] | None = None
) -> dict[str, Any]:
    items = [_view(p) for p in engine.store.list(status)]
    return {"total": len(items), "items": items}


def _load(engine: Engine, proposal_id: str) -> Proposal:
    proposal = engine.store.get(proposal_id)
    if proposal is None:
        raise _fail("이 제안을 찾을 수 없어요.", 404)
    return proposal


@actions_router.post(
    "/proposals/{proposal_id}/approve", tags=["proposals"], response_model=ProposalView
)
async def approve(proposal_id: str, engine: EngineDep) -> ProposalView:
    try:
        result = await engine.apply(_load(engine, proposal_id))
    except (ProposalError, SetupError) as exc:
        raise _fail(str(exc), 409) from exc
    return _view(result)


@actions_router.post(
    "/proposals/{proposal_id}/reject", tags=["proposals"], response_model=ProposalView
)
async def reject(proposal_id: str, engine: EngineDep) -> ProposalView:
    try:
        result = await engine.reject(_load(engine, proposal_id))
    except ProposalError as exc:
        raise _fail(str(exc), 409) from exc
    return _view(result)


class BatchApprove(BaseModel):
    ids: list[str]


@actions_router.post("/proposals/approve", tags=["proposals"])
async def approve_batch(body: BatchApprove, engine: EngineDep) -> dict[str, Any]:
    results = []
    for proposal_id in body.ids:
        proposal = engine.store.get(proposal_id)
        if proposal is None or proposal.status != "pending":
            continue
        if proposal.approval == "individual":
            continue  # personal memory and promoted insights are never batch-approved
        results.append(_view(await engine.apply(proposal)))
    return {"items": results}


# ------------------------------------------------------------------- history


@actions_router.get("/history", tags=["history"])
def get_history(engine: EngineDep, limit: int = 50) -> dict[str, Any]:
    if engine.brain is None:
        return {"items": []}
    entries = history.log(engine.brain, limit=max(1, min(limit, 200)))
    undone = {e.undoes for e in entries if e.undoes}
    return {
        "items": [
            {
                "id": e.id,
                "title": e.title,
                "committed_at": e.committed_at,
                "paths": list(e.paths),
                "undoes": e.undoes,
                "undone": e.id in undone,
            }
            for e in entries
        ]
    }


@actions_router.post("/history/{commit_id}/undo", tags=["history"])
async def undo(commit_id: str, engine: EngineDep) -> dict[str, Any]:
    if not commit_id.isalnum():
        raise _fail("이 변경을 찾을 수 없어요.", 404)
    try:
        sha = await engine.undo(commit_id)
    except history.HistoryError as exc:
        raise _fail(str(exc), 409) from exc
    except SetupError as exc:
        raise _fail(str(exc)) from exc
    return {"commit": sha}
