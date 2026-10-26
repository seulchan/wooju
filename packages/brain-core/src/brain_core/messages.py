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
