"""Routes that change things: setup and settings, adding files, approvals, undo.

Every write goes through :class:`app.engine.Engine`. Messages in ``detail`` are
written for the person using the app, in the app's language (``ko``/``en``).
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import sys
import webbrowser
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel

from brain_core import history
from brain_core.changes import Proposal, ProposalError
from brain_core.messages import UserFacingError, render
from wooju_agents.ask import AskError
from wooju_agents.challenge import ChallengeError
from wooju_agents.llm import (
    ANTHROPIC_DEFAULT_MODEL,
    OLLAMA_MODEL_LARGE,
    OLLAMA_MODEL_SMALL,
    OPENAI_DEFAULT_MODEL,
    LLMError,
    OllamaProvider,
    recommended_ollama_model,
)

from .. import claude_link
from .. import settings as app_settings
from ..engine import Engine, SetupError

actions_router = APIRouter(prefix="/api")


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


EngineDep = Annotated[Engine, Depends(get_engine)]


def _fail(engine: Engine, key: str, status: int = 400, **params: Any) -> HTTPException:
    return HTTPException(status_code=status, detail=render(key, engine.language(), **params))


def _fail_from(engine: Engine, exc: UserFacingError, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail=exc.localized(engine.language()))


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


def _ai_status(engine: Engine) -> AiStatus:
    lang = engine.language()
    ai = app_settings.load().ai
    if ai.provider == "ollama":
        model = ai.model or recommended_ollama_model()
        status = OllamaProvider(model, host=ai.ollama_host).status()
        if not status["running"]:
            message = render("ai.ollama_missing", lang)
        elif not status["model_ready"]:
            message = render("ai.model_needed", lang, model=model)
        else:
            message = None
        result = AiStatus(
            provider="ollama",
            model=model,
            ready=status["running"] and status["model_ready"],
            ollama_running=status["running"],
            model_downloaded=status["model_ready"],
            message=message,
        )
    else:
        default = OPENAI_DEFAULT_MODEL if ai.provider == "openai" else ANTHROPIC_DEFAULT_MODEL
        has_key = app_settings.get_api_key(ai.provider) is not None
        result = AiStatus(
            provider=ai.provider,
            model=ai.model or default,
            ready=has_key,
            has_key=has_key,
            message=None if has_key else render("ai.key_needed", lang),
        )
    pull = engine.pull_state
    if pull["model"] == result.model:
        result.pulling = pull["state"] == "pulling"
        if pull["state"] == "failed" and not result.ready:
            result.message = pull["message"]
    return result


@actions_router.get("/setup", tags=["setup"], response_model=SetupStatus)
def setup_status(engine: EngineDep) -> SetupStatus:
    return SetupStatus(
        brain_path=str(engine.brain) if engine.brain else None,
        brain_ready=engine.brain is not None,
        language=engine.language(),
        ai=_ai_status(engine),
    )


class PullRequest(BaseModel):
    model: str | None = None  # None → the model currently chosen in settings


@actions_router.post("/setup/ai/pull", tags=["setup"])
async def pull_model(engine: EngineDep, body: PullRequest | None = None) -> dict[str, Any]:
    """Download a local model through Ollama (no terminal needed)."""
    await engine.pull_model(body.model if body else None)
    return dict(engine.pull_state)


_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,100}$")


@actions_router.get("/setup/ai/models", tags=["setup"])
def ai_models(engine: EngineDep) -> dict[str, Any]:
    """Local models installed in Ollama, plus the ones Wooju recommends."""
    ai = app_settings.load().ai
    recommended = recommended_ollama_model()
    installed = OllamaProvider(recommended, host=ai.ollama_host).installed()
    names = {m["name"] for m in installed or []}
    suggested = [
        {
            "name": name,
            "recommended": name == recommended,
            "installed": name in names,
            "note": "8 GB" if name == OLLAMA_MODEL_SMALL else "16 GB+",
        }
        for name in (OLLAMA_MODEL_SMALL, OLLAMA_MODEL_LARGE)
    ]
    current = (ai.model or recommended) if ai.provider == "ollama" else None
    return {
        "running": installed is not None,
        "provider": ai.provider,
        "current": current,
        "recommended": recommended,
        "installed": [
            {**m, "recommended": m["name"] == recommended}
            for m in sorted(installed or [], key=lambda m: m["name"])
        ],
        "suggested": suggested,
    }


class ChooseBrain(BaseModel):
    path: str


@actions_router.post("/setup/brain", tags=["setup"])
async def choose_brain(body: ChooseBrain, engine: EngineDep) -> dict[str, Any]:
    if not body.path.strip():
        raise _fail(engine, "setup.choose_folder")
    try:
        created = await engine.choose_brain(Path(body.path.strip()))
    except SetupError as exc:
        raise _fail_from(engine, exc) from exc
    return {"brain_path": str(engine.brain), "created": created}


@actions_router.post("/setup/pick-folder", tags=["setup"])
def pick_folder(engine: EngineDep) -> dict[str, str | None]:
    """Show the Mac's own folder chooser and return the chosen path (None if cancelled)."""
    if sys.platform != "darwin":
        return {"path": None}
    prompt = "Wooju 폴더 고르기" if engine.language() == "ko" else "Choose a folder for Wooju"
    script = (
        f'POSIX path of (choose folder with prompt "{prompt}" '
        "default location (path to documents folder))"
    )
    try:
        out = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True, timeout=600
        )
    except (OSError, subprocess.SubprocessError):
        return {"path": None}
    path = out.stdout.strip()
    return {"path": path.rstrip("/") or None if out.returncode == 0 else None}


class ChooseAi(BaseModel):
    provider: Literal["ollama", "openai", "anthropic"]
    model: str | None = None
    api_key: str | None = None


@actions_router.post("/setup/ai", tags=["setup"], response_model=AiStatus)
async def choose_ai(body: ChooseAi, engine: EngineDep) -> AiStatus:
    model = (body.model or "").strip() or None
    if model and not _MODEL_NAME.match(model):
        raise _fail(engine, "setup.bad_model")
    if body.provider != "ollama" and body.api_key:
        try:
            app_settings.set_api_key(body.provider, body.api_key.strip())
        except app_settings.KeyStoreError as exc:
            raise _fail(engine, "ai.keychain") from exc
    current = app_settings.load()
    current.ai.provider = body.provider
    current.ai.model = model
    app_settings.save(current)
    status = _ai_status(engine)
    if body.provider != "ollama" and status.ready:
        try:  # connection test with a tiny request
            engine.provider().generate_json(
                "Reply with JSON.",
                "Say ok.",
                {"type": "object", "properties": {"ok": {"type": "boolean"}}},
            )
        except LLMError as exc:
            status.ready, status.message = False, exc.localized(engine.language())
    if status.ready:
        await engine.retry_waiting()
    return status


# Pages the app may open in the user's browser. Anything else is refused, so a
# compromised page cannot use this to launch arbitrary URLs or programs.
OPENABLE_URLS = {
    "https://ollama.com/download",
    "https://ollama.com/search",
    "https://console.anthropic.com/settings/keys",
    "https://platform.openai.com/api-keys",
    "https://claude.ai/download",
    "https://t.me/BotFather",
}
# The user's own bot, optionally with this Mac's pairing code.
_TELEGRAM_LINK = re.compile(r"https://t\.me/[A-Za-z0-9_]{5,32}(\?start=[A-Za-z0-9]{6,32})?")


class OpenUrl(BaseModel):
    url: str


@actions_router.post("/open", tags=["setup"])
def open_url(body: OpenUrl, engine: EngineDep) -> dict[str, bool]:
    """Open an allowed page in the default browser (the desktop window cannot)."""
    if body.url not in OPENABLE_URLS and not _TELEGRAM_LINK.fullmatch(body.url):
        raise _fail(engine, "open.refused", 403)
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
            refused.append({"file": upload.filename, "message": exc.localized(engine.language())})
            continue
        job = await engine.enqueue(rel)
        added.append(job.to_dict())
    if not added and refused and engine.brain is None:
        raise HTTPException(status_code=400, detail=refused[0]["message"])
    return {"added": added, "refused": refused}


class CaptureText(BaseModel):
    text: str


@actions_router.post("/capture", tags=["inbox"])
async def capture_text(body: CaptureText, engine: EngineDep) -> dict[str, Any]:
    """Save a pasted link (fetched and organized) or a memo (kept as written)."""
    from wooju_agents.capture import CaptureError

    try:
        return await engine.receive_text(body.text, via="app")
    except (CaptureError, SetupError) as exc:
        raise _fail_from(engine, exc) from exc


# ------------------------------------------------------------ phone capture


def _capture_status(engine: Engine) -> dict[str, Any]:
    from .. import icloud

    cap = app_settings.load().capture
    bot = engine.telegram_bot_name
    paired = cap.telegram_chat_id is not None
    return {
        "icloud": {
            "available": icloud.available(),
            "enabled": cap.icloud,
            "folder": str(icloud.capture_folder()),
        },
        "telegram": {
            "enabled": cap.telegram,
            "bot": bot,
            "paired": paired,
            "pair_link": (
                f"https://t.me/{bot}?start={engine.telegram_pair_code}"
                if cap.telegram and bot and not paired
                else None
            ),
        },
        "recent": engine.capture_log[:10],
    }


@actions_router.get("/capture/status", tags=["inbox"])
def capture_status(engine: EngineDep) -> dict[str, Any]:
    return _capture_status(engine)


class Toggle(BaseModel):
    enabled: bool


@actions_router.post("/capture/icloud", tags=["inbox"])
def set_icloud(body: Toggle, engine: EngineDep) -> dict[str, Any]:
    from .. import icloud

    if body.enabled:
        if not icloud.available():
            raise _fail(engine, "icloud.unavailable")
        icloud.ensure_folder()
    current = app_settings.load()
    current.capture.icloud = body.enabled
    app_settings.save(current)
    return _capture_status(engine)


class TelegramToken(BaseModel):
    token: str


@actions_router.post("/capture/telegram", tags=["inbox"])
async def set_telegram(body: TelegramToken, engine: EngineDep) -> dict[str, Any]:
    """Check the bot token, keep it in the keychain, and wait for pairing."""
    from .. import telegram

    token = body.token.strip()
    if not re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{30,}", token):
        raise _fail(engine, "telegram.bad_token")
    try:
        me = await asyncio.to_thread(engine.telegram_factory(token).me)
    except telegram.TelegramError as exc:
        raise _fail(engine, "telegram.bad_token") from exc
    try:
        app_settings.set_api_key(telegram.KEY_NAME, token)
    except app_settings.KeyStoreError as exc:
        raise _fail(engine, "ai.keychain") from exc
    current = app_settings.load()
    current.capture.telegram = True
    current.capture.telegram_chat_id = None
    app_settings.save(current)
    engine.telegram_bot_name = me.get("username")
    engine.telegram_pair_code = telegram.new_pairing_code()
    telegram.save_state({})
    await engine.start_telegram()
    return _capture_status(engine)


@actions_router.post("/capture/telegram/off", tags=["inbox"])
async def telegram_off(engine: EngineDep) -> dict[str, Any]:
    from .. import telegram

    current = app_settings.load()
    current.capture.telegram = False
    current.capture.telegram_chat_id = None
    app_settings.save(current)
    app_settings.delete_api_key(telegram.KEY_NAME)
    engine.telegram_bot_name = None
    telegram.save_state({})
    await engine.start_telegram()  # stops the loop
    return _capture_status(engine)


@actions_router.post("/inbox/process", tags=["inbox"])
async def process_inbox(engine: EngineDep) -> dict[str, Any]:
    try:
        jobs = await engine.enqueue_inbox()
    except SetupError as exc:
        raise _fail_from(engine, exc) from exc
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
        raise _fail(engine, "proposal.not_found", 404)
    return proposal


@actions_router.post(
    "/proposals/{proposal_id}/approve", tags=["proposals"], response_model=ProposalView
)
async def approve(proposal_id: str, engine: EngineDep) -> ProposalView:
    proposal = _load(engine, proposal_id)
    try:
        result = await engine.apply(proposal)
    except ProposalError as exc:
        raise _fail(engine, "proposal.decided", 409) from exc
    except SetupError as exc:
        raise _fail_from(engine, exc) from exc
    return _view(result)


@actions_router.post(
    "/proposals/{proposal_id}/reject", tags=["proposals"], response_model=ProposalView
)
async def reject(proposal_id: str, engine: EngineDep) -> ProposalView:
    try:
        result = await engine.reject(_load(engine, proposal_id))
    except ProposalError as exc:
        raise _fail(engine, "proposal.decided", 409) from exc
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

_RECEIVED_MANY = re.compile(r"^Received (\d+) file\(s\)$")


def display_title(title: str, lang: str) -> str:
    """History titles are stored in English in git; show them in the app's language."""
    if lang != "ko":
        return title
    if title == "Start this Brain":
        return "Brain 시작"
    if title == "Save your own edits":
        return "직접 고친 내용 저장"
    if title.startswith("Undo: "):
        return f"되돌림: {display_title(title.removeprefix('Undo: '), lang)}"
    if m := _RECEIVED_MANY.match(title):
        return f"파일 {m.group(1)}개 받음"
    if title.startswith("Received "):
        return f"받은 파일: {title.removeprefix('Received ')}"
    return title


# ------------------------------------------------------- ask, challenge


class AskRequest(BaseModel):
    question: str


def _ai_fail(engine: Engine, exc: LLMError) -> HTTPException:
    # "Not ready yet" (Ollama off, model missing, no key) is 503; the UI shows
    # the message with the setup hint. Other AI failures are 502.
    return _fail_from(engine, exc, 503 if exc.retryable else 502)


@actions_router.post("/ask", tags=["ask"])
async def ask_question(body: AskRequest, engine: EngineDep) -> dict[str, Any]:
    try:
        answer = await engine.ask(body.question)
    except LLMError as exc:
        raise _ai_fail(engine, exc) from exc
    except (AskError, SetupError) as exc:
        raise _fail_from(engine, exc) from exc
    return answer.to_dict()


class ChallengeRequest(BaseModel):
    id: str


@actions_router.post("/challenge", tags=["ask"], response_model=ProposalView)
async def challenge(body: ChallengeRequest, engine: EngineDep) -> ProposalView:
    try:
        proposal = await engine.challenge(body.id)
    except LLMError as exc:
        raise _ai_fail(engine, exc) from exc
    except ChallengeError as exc:
        raise _fail_from(engine, exc, 404 if exc.key == "challenge.not_found" else 400) from exc
    except SetupError as exc:
        raise _fail_from(engine, exc) from exc
    return _view(proposal)


# ------------------------------------------------------------ meaning search


@actions_router.get("/search/status", tags=["setup"])
async def search_status(engine: EngineDep) -> dict[str, Any]:
    """Meaning search: is the embedding model there, and how much is indexed."""
    from wooju_agents.embed import EMBED_MODEL

    await engine.refresh_vectors()
    state = dict(engine.search_state)
    pulling = (
        engine.pull_state.get("model") == EMBED_MODEL
        and engine.pull_state.get("state") == "pulling"
    )
    return {"model": EMBED_MODEL, "pulling": pulling, **state}


# ---------------------------------------------------------------- maintainer


class ReviewDate(BaseModel):
    id: str
    until: date | None = None  # None clears the review date


@actions_router.post("/review-date", tags=["maintainer"], response_model=ProposalView)
async def set_review_date(body: ReviewDate, engine: EngineDep) -> ProposalView:
    """The user reviewed a note: set its next review date, or clear it."""
    try:
        proposal = await engine.set_review_date(body.id, body.until)
    except SetupError as exc:
        raise _fail_from(engine, exc, 404 if exc.key == "review.not_found" else 400) from exc
    if proposal.status != "applied":
        raise _fail(engine, "review.failed")
    return _view(proposal)


# -------------------------------------------------------- Claude connection


@actions_router.get("/claude", tags=["claude"])
def claude_status() -> dict[str, Any]:
    return claude_link.status()


@actions_router.post("/claude/connect", tags=["claude"])
def claude_connect(engine: EngineDep) -> dict[str, Any]:
    if engine.brain is None:
        raise _fail(engine, "setup.brain_first")
    try:
        return claude_link.connect()
    except claude_link.ClaudeLinkError as exc:
        raise _fail_from(engine, exc) from exc


@actions_router.post("/claude/disconnect", tags=["claude"])
def claude_disconnect(engine: EngineDep) -> dict[str, Any]:
    try:
        return claude_link.disconnect()
    except claude_link.ClaudeLinkError as exc:
        raise _fail_from(engine, exc) from exc


@actions_router.get("/history", tags=["history"])
def get_history(engine: EngineDep, limit: int = 50) -> dict[str, Any]:
    if engine.brain is None:
        return {"items": []}
    lang = engine.language()
    entries = history.log(engine.brain, limit=max(1, min(limit, 200)))
    undone = {e.undoes for e in entries if e.undoes}
    return {
        "items": [
            {
                "id": e.id,
                "title": display_title(e.title, lang),
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
        raise _fail(engine, "history.not_found", 404)
    try:
        sha = await engine.undo(commit_id)
    except history.HistoryError as exc:
        raise _fail_from(engine, exc, 409) from exc
    except SetupError as exc:
        raise _fail_from(engine, exc) from exc
    return {"commit": sha}
