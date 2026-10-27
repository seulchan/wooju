"""Messages people see in the app, in every supported language.

Code raises errors and sets job text with a message *key*; whoever talks to the
user renders it in the user's language (``ko`` or ``en``, see
docs/DECISIONS.md). Unknown keys render as themselves, so a plain sentence can
still be passed where no key exists yet.
"""

from __future__ import annotations

from typing import Any

MESSAGES: dict[str, tuple[str, str]] = {
    # ingest
    "ingest.inbox_only": (
        "받은 편지함에 있는 파일만 정리할 수 있어요.",
        "Only files in the inbox can be organized.",
    ),
    "ingest.unsupported": (
        "이 파일 형식은 아직 읽을 수 없어요. PDF, 텍스트, HTML 파일을 넣어 주세요.",
        "This file type can't be read yet. Add PDF, text, or HTML files.",
    ),
    "ingest.no_text": (
        "파일에서 글자를 찾지 못했어요. 스캔한 PDF는 아직 지원하지 않아요.",
        "No text was found in this file. Scanned PDFs aren't supported yet.",
    ),
    "ingest.bad_shape": (
        "AI가 정리한 결과가 형식에 맞지 않아요. 다시 시도해 주세요.",
        "The AI's result didn't have the right shape. Please try again.",
    ),
    # ask
    "ask.empty": ("질문을 입력해 주세요.", "Type a question first."),
    "ask.too_long": (
        "질문이 너무 길어요. 1,000자 안으로 줄여 주세요.",
        "The question is too long. Keep it under 1,000 characters.",
    ),
    "ask.bad_shape": (
        "AI의 답이 형식에 맞지 않아요. 다시 물어봐 주세요.",
        "The AI's answer didn't have the right shape. Please ask again.",
    ),
    # capture
    "capture.empty": ("보낼 내용이 없어요.", "There's nothing to save."),
    "capture.bad_link": (
        "이 링크는 열 수 없어요. 인터넷 주소(http, https)만 받을 수 있어요.",
        "This link can't be opened. Only web addresses (http, https) can be saved.",
    ),
    "capture.unreachable": (
        "링크 페이지를 가져오지 못했어요. 주소와 인터넷 연결을 확인해 주세요.",
        "Couldn't fetch the page. Check the address and your internet connection.",
    ),
    "capture.unsupported_link": (
        "이 링크는 웹 페이지나 PDF가 아니라서 저장하지 못했어요.",
        "This link isn't a web page or PDF, so it couldn't be saved.",
    ),
    "capture.too_big": (
        "링크 파일이 너무 커요 (15MB까지).",
        "The linked file is too big (15 MB at most).",
    ),
    "icloud.unavailable": (
        "이 Mac에서 iCloud Drive가 꺼져 있어요. "
        "시스템 설정 > Apple 계정 > iCloud에서 iCloud Drive를 켜 주세요.",
        "iCloud Drive is off on this Mac. Turn it on in System Settings > Apple Account > iCloud.",
    ),
    "open.no_file": (
        "그 파일이 Brain 폴더에 없어요. 옮겨졌거나 지워졌을 수 있어요.",
        "That file isn't in the Brain folder. It may have been moved or deleted.",
    ),
    "llm.busy": (
        "이 Mac의 메모리가 부족해서 AI가 멈췄어요. 잠시 후 자동으로 다시 정리할게요. "
        "다른 큰 앱을 닫으면 도움이 돼요.",
        "The AI stopped because this Mac ran low on memory. It will try again shortly; "
        "closing other large apps helps.",
    ),
    "job.gave_up": (
        "세 번 시도했지만 정리하지 못했어요. 파일은 받은 편지함에 남아 있어요. "
        "나중에 '다시 시도'를 눌러 주세요.",
        "Tried three times without success. The file is still in the inbox; "
        "press 'Try again' later.",
    ),
    "job.conflicts": (
        "기존 노트와 맞지 않는 내용 {count}건 — 홈에서 확인해 주세요.",
        "{count} disagreement(s) with existing notes; see Home.",
    ),
    "job.duplicate": ("이미 저장된 자료예요: {title}", "Already saved: {title}"),
    "job.removed": ("받은 편지함에서 지웠어요.", "Removed from the inbox."),
    # telegram
    "telegram.paired": (
        "연결됐어요. 이제 링크, 메모, 파일(PDF, 텍스트, HTML)을 보내면 Wooju에 저장해요. "
        "Mac에서 Wooju가 열려 있을 때 처리돼요.",
        "Connected. Send links, memos, or files (PDF, text, HTML) and Wooju saves them. "
        "They're handled while Wooju is open on your Mac.",
    ),
    "telegram.pair_first": (
        "아직 연결 전이에요. Mac의 Wooju 설정에서 'Telegram 열기'를 눌러 연결해 주세요.",
        "Not connected yet. In Wooju's Settings on your Mac, press 'Open Telegram' to connect.",
    ),
    "telegram.private": ("이 봇은 개인용이에요.", "This bot is private."),
    "telegram.received": (
        "받았어요: {name}. 정리하는 중이에요.",
        "Got it: {name}. Organizing it now.",
    ),
    "telegram.memo": ("메모를 저장했어요.", "Memo saved."),
    "telegram.link": (
        "링크를 받았어요. 페이지를 정리하는 중이에요.",
        "Link received. Organizing the page.",
    ),
    "telegram.saved": ("✓ 저장했어요: {title}", "✓ Saved: {title}"),
    "telegram.failed": (
        "✗ 정리하지 못했어요: {error}\n"
        "파일은 Wooju 받은 편지함에 남아 있어서 Mac에서 다시 시도할 수 있어요.",
        "✗ Couldn't organize it: {error}\n"
        "The file stays in Wooju's inbox so you can try again on the Mac.",
    ),
    "telegram.waiting": (
        "AI가 준비되면 정리할게요. Mac에서 Ollama가 켜져 있는지 확인해 주세요.",
        "It'll be organized once the AI is ready. Check that Ollama is running on your Mac.",
    ),
    "telegram.no_photos": (
        "사진은 아직 읽지 못해요. PDF나 링크로 보내 주세요.",
        "Photos can't be read yet. Send a PDF or a link instead.",
    ),
    "telegram.help": (
        "링크나 메모를 그냥 보내거나, 파일(PDF, 텍스트, HTML)을 보내 주세요.",
        "Just send a link or a memo, or a file (PDF, text, HTML).",
    ),
    "telegram.download_failed": (
        "파일을 받지 못했어요. 20MB보다 작은 파일만 받을 수 있어요.",
        "Couldn't get the file. Files must be under 20 MB.",
    ),
    "telegram.bad_token": (
        "토큰이 맞지 않아요. @BotFather가 준 토큰 전체를 붙여 넣어 주세요.",
        "That token didn't work. Paste the whole token @BotFather gave you.",
    ),
    # edits
    "note.changed": (
        "그사이에 이 노트가 다른 곳에서 바뀌었어요. 덮어쓰지 않았어요. "
        "새로 불러온 뒤 다시 고쳐 주세요.",
        "This note changed elsewhere in the meantime, so nothing was overwritten. "
        "Reload it and edit again.",
    ),
    "note.title": ("제목을 적어 주세요.", "Give the note a title."),
    "note.grounds": (
        "생각의 근거가 된 노트를 하나 이상 골라 주세요.",
        "Pick at least one note this thought rests on.",
    ),
    "note.empty": (
        "본문이 비어 있으면 저장할 수 없어요.",
        "A note can't be saved with an empty body.",
    ),
    "note.invalid": (
        "저장하면 노트 규칙에 어긋나서 저장하지 않았어요: {error}",
        "Not saved, because it would break the note rules: {error}",
    ),
    "status.step": (
        "{current}에서 {status}(으)로는 바로 바꿀 수 없어요. 한 단계씩 바꿔 주세요.",
        "An insight can't go from {current} to {status} directly; move one step at a time.",
    ),
    "status.needs_challenge": (
        "잠정으로 올리려면 먼저 반론 검토를 해서 노트에 반론(Challenge) 섹션이 있어야 해요.",
        "To make it provisional, challenge it first so the note has a Challenge section.",
    ),
    "retire.replacement": (
        "대신할 노트를 찾을 수 없어요. 다른 노트를 골라 주세요.",
        "That replacement note can't be used. Please pick another.",
    ),
    "retire.reason": (
        "폐기하는 이유를 적어 주세요. 나중에 왜 버렸는지 알 수 있어요.",
        "Write why it's being retired, so you know later.",
    ),
    # maintainer
    "review.not_found": ("그 노트를 찾지 못했어요.", "That note wasn't found."),
    "review.unreadable": (
        "노트 앞부분(frontmatter)이 깨져 있어서 날짜를 바꾸지 못했어요.",
        "The note's frontmatter is broken, so the date couldn't be changed.",
    ),
    "review.failed": (
        "날짜를 바꾸면 노트 규칙에 어긋나서 저장하지 않았어요.",
        "Changing the date would break the note's rules, so nothing was saved.",
    ),
    # challenger
    "challenge.not_found": ("그 노트를 찾지 못했어요.", "That note wasn't found."),
    "challenge.not_insight": (
        "반론 검토는 발견한 연결(인사이트)에만 할 수 있어요.",
        "Only insights can be challenged.",
    ),
    "challenge.bad_shape": (
        "AI의 검토 결과가 형식에 맞지 않아요. 다시 시도해 주세요.",
        "The AI's review didn't have the right shape. Please try again.",
    ),
    # Claude connection
    "claude.not_installed": (
        "Claude 데스크톱 앱이 없어요. 먼저 설치해 주세요.",
        "The Claude desktop app isn't installed. Install it first.",
    ),
    "claude.config_unreadable": (
        "Claude 설정 파일을 읽지 못해서 바꾸지 않았어요. "
        "Claude 앱의 설정 > 개발자 > 설정 편집에서 파일을 확인해 주세요.",
        "Claude's settings file couldn't be read, so it was left unchanged. "
        "Check it in Claude → Settings → Developer → Edit Config.",
    ),
    # AI providers
    "llm.unreadable": (
        "AI 응답을 읽지 못했어요. 다시 시도해 주세요.",
        "Couldn't read the AI's answer. Please try again.",
    ),
    "llm.pull_failed": (
        "모델을 받지 못했어요. 인터넷 연결과 Ollama 실행 여부를 확인해 주세요.",
        "Couldn't download the model. Check your internet connection and that Ollama is running.",
    ),
    "llm.ollama_off": (
        "Ollama가 실행 중이 아니에요. Ollama 앱을 열어 주세요.",
        "Ollama isn't running. Please open the Ollama app.",
    ),
    "llm.model_missing": (
        "AI 모델({model})을 아직 받지 않았어요.",
        "The AI model ({model}) hasn't been downloaded yet.",
    ),
    "llm.no_response": (
        "AI가 응답하지 않았어요. 잠시 후 다시 시도해 주세요.",
        "The AI didn't respond. Please try again in a moment.",
    ),
    "llm.openai_key": (
        "OpenAI API 키가 맞지 않아요. 설정에서 다시 입력해 주세요.",
        "The OpenAI API key isn't valid. Enter it again in Settings.",
    ),
    "llm.openai_down": (
        "OpenAI가 응답하지 않았어요. 잠시 후 다시 시도해 주세요.",
        "OpenAI didn't respond. Please try again in a moment.",
    ),
    "llm.claude_key": (
        "Claude API 키가 맞지 않아요. 설정에서 다시 입력해 주세요.",
        "The Claude API key isn't valid. Enter it again in Settings.",
    ),
    "llm.claude_down": (
        "Claude가 응답하지 않았어요. 잠시 후 다시 시도해 주세요.",
        "Claude didn't respond. Please try again in a moment.",
    ),
    "llm.offline": ("인터넷 연결을 확인해 주세요.", "Please check your internet connection."),
    "llm.key_first": ("API 키를 먼저 입력해 주세요.", "Please enter an API key first."),
    # AI status
    "ai.ollama_missing": (
        "Ollama가 설치되지 않았거나 꺼져 있어요.",
        "Ollama isn't installed or isn't running.",
    ),
    "ai.model_needed": (
        "AI 모델({model})을 받아야 해요.",
        "The AI model ({model}) needs to be downloaded.",
    ),
    "ai.key_needed": ("API 키를 입력해 주세요.", "Please enter an API key."),
    "ai.keychain": (
        "키를 안전하게 저장하지 못했어요. Mac의 키체인 접근을 허용해 주세요.",
        "Couldn't store the key safely. Please allow access to the Mac keychain.",
    ),
    # setup and files
    "setup.embedding_model": (
        "이 모델은 의미 검색 전용이라 답을 만들 수 없어요. 다른 모델을 골라 주세요.",
        "This model is for meaning search only and can't write answers. Pick another model.",
    ),
    "job.topics": ("주제에 연결했어요: {titles}", "Filed under: {titles}"),
    "topic.too_few": (
        "주제로 묶으려면 노트가 두 개 이상 필요해요.",
        "A topic needs at least two notes.",
    ),
    "topic.bad_shape": (
        "AI가 주제를 제대로 쓰지 못했어요. 잠시 뒤 다시 시도해 주세요.",
        "The AI couldn't write the topic. Please try again in a moment.",
    ),
    "digest.topics": (
        "주제로 묶을 만한 노트 묶음 {n}개가 있어요",
        "{n} groups of notes could become topics",
    ),
    "job.similar": (
        "비슷한 노트가 이미 있어요: {titles}",
        "A similar note is already in your Brain: {titles}",
    ),
    "digest.title": ("이번 주 Wooju", "Wooju this week"),
    "digest.review_due": ("다시 볼 노트 {n}개: {titles}", "{n} to look at again: {titles}"),
    "digest.conflicts": (
        "다른 노트와 어긋나는 자료 {n}개: {titles}",
        "{n} disagreeing with other notes: {titles}",
    ),
    "digest.grounds_changed": (
        "근거가 바뀐 노트 {n}개: {titles}",
        "{n} whose grounds changed: {titles}",
    ),
    "digest.candidate": (
        "아직 검토 전인 생각 {n}개: {titles}",
        "{n} ideas not yet challenged: {titles}",
    ),
    "digest.open_questions": ("열린 질문 {n}개: {titles}", "{n} open questions: {titles}"),
    "digest.more": (" 외 {n}개", " and {n} more"),
    "digest.open_app": (
        "Wooju 홈 화면에서 확인할 수 있어요.",
        "You'll find them on Wooju's Home screen.",
    ),
    "samples.present": (
        "예시 노트가 이미 들어 있어요.",
        "The sample notes are already in your Brain.",
    ),
    "samples.none": ("지울 예시 노트가 없어요.", "There are no sample notes to remove."),
    "samples.failed": (
        "예시 노트를 넣지 못했어요. 잠시 뒤 다시 시도해 주세요.",
        "The sample notes couldn't be added. Please try again in a moment.",
    ),
    "setup.bad_model": ("모델 이름이 올바르지 않아요.", "That model name isn't valid."),
    "setup.choose_folder": ("폴더를 골라 주세요.", "Please choose a folder."),
    "setup.not_folder": (
        "파일이 아니라 폴더를 골라 주세요.",
        "Please choose a folder, not a file.",
    ),
    "setup.folder_busy": (
        "이 폴더에는 이미 다른 파일이 있어요. 빈 폴더나 새 폴더를 골라 주세요.",
        "This folder already has other files. Choose an empty or new folder.",
    ),
    "setup.broken_install": (
        "앱 설치가 손상됐어요. 앱을 다시 설치해 주세요.",
        "The app installation is damaged. Please reinstall the app.",
    ),
    "setup.brain_first": (
        "먼저 저장할 폴더를 골라 주세요.",
        "Please choose a folder to keep things in first.",
    ),
    "upload.unsupported": (
        "'{name}'은(는) 아직 읽을 수 없는 형식이에요. PDF, 텍스트, HTML 파일을 넣어 주세요.",
        "'{name}' can't be read yet. Add PDF, text, or HTML files.",
    ),
    "open.refused": ("이 주소는 열 수 없어요.", "This address can't be opened."),
    # jobs
    "job.failed": ("정리하지 못했어요: {error}", "Couldn't organize this file: {error}"),
    "job.gone": ("파일이 더 이상 받은 편지함에 없어요.", "The file is no longer in the inbox."),
    "job.waiting": (
        "AI가 준비되면 자동으로 정리해요.",
        "This will be organized automatically once the AI is ready.",
    ),
    "job.invalid": (
        "정리 결과가 규칙에 맞지 않아 저장하지 않았어요.",
        "The result didn't follow the Brain's rules, so it wasn't saved.",
    ),
    # proposals and history
    "proposal.not_found": ("이 제안을 찾을 수 없어요.", "This proposal can't be found."),
    "proposal.decided": ("이미 처리된 제안이에요.", "This proposal has already been handled."),
    "history.not_found": ("이 변경을 찾을 수 없어요.", "This change can't be found."),
    "history.first": (
        "Brain의 첫 기록은 되돌릴 수 없어요.",
        "The first entry of a Brain can't be undone.",
    ),
    "history.changed_again": (
        "'{path}'이(가) 그 뒤에 다시 바뀌어서 되돌리지 않았어요.",
        "'{path}' changed again after this change, so it was not undone.",
    ),
}

LANGS = ("ko", "en")


def render(key: str, lang: str = "ko", **params: Any) -> str:
    """Render ``key`` in ``lang`` (``ko`` or ``en``); unknown keys pass through."""
    pair = MESSAGES.get(key)
    if pair is None:
        return key.format(**params) if params else key
    text = pair[1] if lang == "en" else pair[0]
    return text.format(**params) if params else text


class UserFacingError(Exception):
    """An error whose message is meant for the person using the app.

    ``key`` is a :data:`MESSAGES` key (or a plain sentence). ``user_message`` is
    the Korean rendering, kept for callers that do not know the language;
    :meth:`localized` renders it for a given language.
    """

    def __init__(self, detail: str, key: str, **params: Any) -> None:
        super().__init__(detail)
        self.key = key
        self.params = params

    @property
    def user_message(self) -> str:
        return render(self.key, "ko", **self.params)

    def localized(self, lang: str) -> str:
        return render(self.key, lang, **self.params)
