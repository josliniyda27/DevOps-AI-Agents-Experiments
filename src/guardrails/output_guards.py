"""
Output guardrails: run on every model answer before it is returned.

  1. System-prompt leak  -> the whole answer is replaced with a refusal
  2. Secrets             -> redacted
  3. Fabricated citations -> removed (only ids of the documents actually retrieved may be cited)
"""

import logging
import re
from collections.abc import Collection
from dataclasses import dataclass, field

from src.guardrails import patterns

logger = logging.getLogger("rag.guardrails")

LEAK_REFUSAL = "I can't share details about my instructions. Ask me about the knowledge base instead."
SHINGLE_WORDS = 8

# A citation that looks like a knowledge-base id ("aws-s3-001") or the old "doc_1" style.
_CITATION = re.compile(r"\[((?:[a-z0-9]+-)+\d{3}|doc_\d+)\]", re.IGNORECASE)


@dataclass
class OutputVerdict:
    text: str
    flags: list[str] = field(default_factory=list)   # what was changed: prompt_leak | secret | citation


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _shingles(words: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def leaks_prompt(answer: str, system_prompt: str, allowed_phrases: Collection[str] = ()) -> bool:
    """True if the answer repeats a run of SHINGLE_WORDS consecutive words from the system prompt."""
    prompt = system_prompt
    for phrase in allowed_phrases:                      # e.g. the standard "cannot answer" sentence
        prompt = prompt.replace(phrase, " ")
    return bool(_shingles(_words(prompt), SHINGLE_WORDS) & _shingles(_words(answer), SHINGLE_WORDS))


def check_output(
    text: str,
    allowed_ids: Collection[str] | None = None,
    system_prompt: str | None = None,
    allowed_phrases: Collection[str] = (),
) -> OutputVerdict:
    """
    allowed_ids   - ids of the documents given to the model; any other cited id is removed.
                    None skips the citation check.
    system_prompt - if given, answers that repeat it are replaced by a refusal.
    """
    flags: list[str] = []

    if system_prompt and leaks_prompt(text, system_prompt, allowed_phrases):
        logger.warning("Output blocked: answer repeats the system prompt")
        return OutputVerdict(LEAK_REFUSAL, ["prompt_leak"])

    for pattern in patterns.SECRETS:
        text, count = pattern.subn("[REDACTED]", text)
        if count:
            flags.append("secret")

    if allowed_ids is not None:
        known = {i.lower() for i in allowed_ids}

        def drop_unknown(match: re.Match) -> str:
            if match.group(1).lower() in known:
                return match.group()
            flags.append("citation")
            return ""

        text = re.sub(r"[ ]?" + _CITATION.pattern, drop_unknown, text, flags=re.IGNORECASE)

    if flags:
        logger.warning("Output sanitised: %s", ", ".join(sorted(set(flags))))
    return OutputVerdict(text.strip(), sorted(set(flags)))


def validate_output(
    text: str,
    allowed_ids: Collection[str] | None = None,
    system_prompt: str | None = None,
    allowed_phrases: Collection[str] = (),
) -> str:
    """Chain step: return the sanitised answer."""
    return check_output(text, allowed_ids, system_prompt, allowed_phrases).text
