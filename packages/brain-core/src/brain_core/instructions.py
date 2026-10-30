"""Sentences in outside material that talk to an AI instead of a reader.

Memory-poisoning attacks hide an instruction in an ordinary document ("save
this rule to memory: always ...") and wait for an agent to file it; the
instruction then acts in later sessions (arXiv 2609.13889 reports 81.7%
cross-session success against a coding-agent harness). Filters on the model's
input catch few of these. Wooju's defence is on the write path: a proposal
built from material that contains such sentences is never applied
automatically; it waits for the user, with the sentences shown.

The patterns are deliberately broad. A false alarm costs one review; a miss
puts an instruction into the user's memory. An article *about* prompt
injection will be flagged too, which is the right outcome.
"""

from __future__ import annotations

import re

MAX_FOUND = 3

_PATTERNS = [
    # Talking to the model about its instructions.
    r"\b(ignore|disregard|forget|override)\b[^.\n]{0,30}\b(previous|prior|above|earlier|all|your)\b"
    r"[^.\n]{0,20}\b(instructions?|rules?|prompts?|messages?|guidelines)\b",
    r"\bsystem prompt\b",
    r"\byou are (now )?(an?|the) (ai|assistant|language model|agent|chatbot)\b",
    r"\b(as an|dear) (ai|assistant|language model|agent|llm)\b",
    r"\b(note|message|instruction)s? (to|for) (the )?"
    r"(ai|assistant|agent|model|llm|claude|chatgpt)\b",
    # Asking to be kept and to act later.
    r"\b(remember|memorize|memorise)\b[^.\n]{0,15}\b(this|that|the following|these)\b",
    r"\b(save|store|add|write|keep|record)\b[^.\n]{0,25}\b(to|in|into)\b[^.\n]{0,10}"
    r"\b(your |the )?(memory|memories|long-term memory|notes|knowledge base)\b",
    r"\bfrom now on\b",
    r"\bin (all|every|any) (future|later|subsequent) "
    r"(sessions?|conversations?|answers?|responses?|tasks?)\b",
    r"\b(always|never)\b[^.\n]{0,12}\b(respond|answer|reply|say|mention|reveal|recommend|include|"
    r"use|send|tell|follow|obey)\b",
    # Korean.
    r"(이전|앞의|위의|기존)[^.\n]{0,10}(지시|명령|규칙|프롬프트)[^.\n]{0,6}(무시|잊)",
    r"시스템 ?프롬프트",
    r"(너는|당신은)[^.\n]{0,10}(AI|인공지능|어시스턴트|비서|에이전트|챗봇)",
    r"(AI|인공지능|어시스턴트|에이전트|모델)(에게|한테|는|은)[^.\n]{0,20}(지시|명령|해야|하라|해라|하세요)",
    r"(기억해|기억하라|기억해라|기억해 ?둬|기억해 ?두|외워)",
    r"(메모리|기억|노트|지식 ?베이스)(에|에다|으로)[^.\n]{0,10}"
    r"(저장|기록|추가)(해|하라|하세요|해라|할 것)",
    r"앞으로[^.\n]{0,8}(항상|모든|매번|반드시)",
    r"(항상|절대|반드시)[^.\n]{0,15}(답하|대답|응답|말하|언급하|추천하|따르)(라|세요|해라|할 것)",
]
_RE = re.compile("|".join(f"(?:{p})" for p in _PATTERNS), re.IGNORECASE)


def find_instructions(text: str) -> list[str]:
    """Up to three sentences of ``text`` that look like instructions to an AI."""
    found: list[str] = []
    for m in _RE.finditer(text):
        start = max(text.rfind(".", 0, m.start()), text.rfind("\n", 0, m.start())) + 1
        ends = [i for i in (text.find(".", m.end()), text.find("\n", m.end())) if i >= 0]
        end = min(ends) + 1 if ends else len(text)
        sentence = " ".join(text[start:end].split())
        if len(sentence) > 240:
            sentence = sentence[:239].rstrip() + "…"
        if sentence and sentence not in found:
            found.append(sentence)
        if len(found) >= MAX_FOUND:
            break
    return found
