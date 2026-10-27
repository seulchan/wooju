"""The Telegram bot: pairing, receiving memos and links, replying."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from brain_core.messages import UserFacingError, render

from .. import settings as app_settings
from .. import telegram
from .base import (
    Job,
    logger,
)


class TelegramBotMixin:
    """Part of :class:`app.engine.Engine`; uses its state (``self.brain``, ``self.index``...)."""

    async def start_telegram(self) -> None:
        """Start (or restart) listening to the user's bot, if it is set up."""
        if self.telegram_task is not None:
            self.telegram_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.telegram_task
            self.telegram_task = None
        if not app_settings.load().capture.telegram:
            return
        token = app_settings.get_api_key(telegram.KEY_NAME)
        if not token:
            return
        bot = self.telegram_factory(token)
        self.telegram_task = asyncio.create_task(self._telegram_loop(bot), name="wooju-telegram")

    async def _telegram_loop(self, bot: Any) -> None:
        state = telegram.load_state()
        offset = state.get("offset")
        if self.telegram_bot_name is None:
            with contextlib.suppress(telegram.TelegramError):
                self.telegram_bot_name = (await asyncio.to_thread(bot.me)).get("username")
        while True:
            try:
                updates = await asyncio.to_thread(bot.updates, offset)
            except telegram.TelegramError as exc:
                logger.info("Telegram unreachable (%s); retrying", exc)
                await asyncio.sleep(15)
                continue
            for update in updates:
                offset = update["update_id"] + 1
                telegram.save_state({"offset": offset})
                message = update.get("message")
                if message:
                    try:
                        await self._telegram_message(bot, message)
                    except Exception:  # noqa: BLE001 — one message must not stop the bot
                        logger.exception("Telegram message failed")

    def _say(self, key: str, **params: Any) -> str:
        return render(key, self.language(), **params)

    async def _telegram_message(self, bot: Any, message: dict[str, Any]) -> None:
        chat_id = message["chat"]["id"]
        text = (message.get("text") or message.get("caption") or "").strip()
        settings = app_settings.load()
        paired = settings.capture.telegram_chat_id
        send = lambda key, **p: asyncio.to_thread(bot.send, chat_id, self._say(key, **p))  # noqa: E731

        if paired is None:
            if telegram.pairing_code_in(text) == self.telegram_pair_code:
                settings.capture.telegram_chat_id = chat_id
                app_settings.save(settings)
                self.telegram_pair_code = telegram.new_pairing_code()
                await send("telegram.paired")
            else:
                await send("telegram.pair_first")
            return
        if chat_id != paired:
            await send("telegram.private")
            return
        if self.brain is None:
            await send("setup.brain_first")
            return

        try:
            if message.get("document"):
                doc = message["document"]
                name = doc.get("file_name") or "file"
                data = await asyncio.to_thread(bot.download, doc["file_id"])
                rel = await self.receive(name, data)
                job = await self.enqueue(rel)
                self._log_capture("telegram", "file", name)
                await send("telegram.received", name=name)
                asyncio.create_task(self._telegram_follow(bot, chat_id, job))
            elif message.get("photo"):
                await send("telegram.no_photos")
            elif text.startswith("/"):
                await send("telegram.help")
            elif text:
                result = await self.receive_text(text, via="telegram")
                self._log_capture("telegram", result["kind"], text[:40])
                if result["kind"] == "memo":
                    await send("telegram.memo")
                elif result.get("duplicate"):
                    await send("job.duplicate", title=result["title"])
                else:
                    await send("telegram.link")
                    job = self.jobs.get(result["job"]["id"])
                    if job:
                        asyncio.create_task(self._telegram_follow(bot, chat_id, job))
        except UserFacingError as exc:
            await asyncio.to_thread(bot.send, chat_id, exc.localized(self.language()))
        except telegram.TelegramError:
            await send("telegram.download_failed")

    async def _telegram_follow(self, bot: Any, chat_id: int, job: Job, wait: float = 2.0) -> None:
        """Tell the chat how a captured item turned out."""
        told_waiting = False
        for _ in range(int(3600 / wait)):
            if job.state == "done":
                if job.proposal_id is None:  # e.g. already saved before
                    text = job.message or self._say("telegram.saved", title=job.title or job.file)
                else:
                    text = self._say("telegram.saved", title=job.title or job.file)
                    if job.conflicts:
                        text += "\n" + self._say("job.conflicts", count=job.conflicts)
                await asyncio.to_thread(bot.send, chat_id, text)
                return
            if job.state == "failed":
                text = self._say("telegram.failed", error=job.message or job.file)
                await asyncio.to_thread(bot.send, chat_id, text)
                return
            if job.state == "waiting" and not told_waiting:
                told_waiting = True
                await asyncio.to_thread(
                    bot.send, chat_id, job.message or self._say("telegram.waiting")
                )
            await asyncio.sleep(wait)
