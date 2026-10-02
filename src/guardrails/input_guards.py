"""
Input guardrails: run on every user question before it reaches retrieval or the LLM.

Order: sanitise -> length -> prompt injection -> harmful intent -> secrets -> redact personal data.
Whether a question is *in scope* is decided later by retrieval (nothing relevant found -> no answer).
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, field

from src.guardrails import patterns

logger = logging.getLogger("rag.guardrails")

MAX_INPUT_CHARS = 1000


@dataclass
class InputVerdict:
    allowed: bool
    text: str                                              # sanitised question (empty if blocked)
    category: str = "ok"                                   # ok | empty | too_long | injection | harmful | secret
    reason: str = ""
    redacted: list[str] = field(default_factory=list)      # kinds of personal data that were masked


class GuardrailViolation(Exception):
    """Raised by validate_input when a question is blocked."""

    def __init__(self, verdict: InputVerdict):
        super().__init__(verdict.reason)
        self.verdict = verdict

    @property
    def category(self) -> str:
        return self.verdict.category

    @property
    def reason(self) -> str:
        return self.verdict.reason


def normalise(text: str) -> str:
    """NFKC-fold look-alike characters, drop control/zero-width characters, collapse whitespace."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch) not in ("Cc", "Cf"))
    return re.sub(r"[ \t]+", " ", text).strip()


_LEET = str.maketrans("013457@$", "oieastas")


def _looks_like_injection(text: str) -> bool:
    """Match injection patterns on the text as written, de-leetspeaked, and with all spacing removed."""
    if any(p.search(text) for p in patterns.INJECTION):
        return True
    folded = text.lower().translate(_LEET)
    if any(p.search(folded) for p in patterns.INJECTION):
        return True
    squashed = re.sub(r"[\W_]+", "", folded)
    return any(p.search(squashed) for p in patterns.INJECTION_SQUASHED)


def _redact_personal_data(text: str) -> tuple[str, list[str]]:
    found = []

    def mask_card(match: re.Match) -> str:
        digits = re.sub(r"\D", "", match.group())
        if 13 <= len(digits) <= 19 and patterns.luhn_valid(digits):
            found.append("card")
            return "[CARD]"
        return match.group()

    text = patterns.CARD_CANDIDATE.sub(mask_card, text)
    for name, pattern, mask in (("email", patterns.EMAIL, "[EMAIL]"), ("ssn", patterns.SSN, "[SSN]")):
        text, count = pattern.subn(mask, text)
        if count:
            found.append(name)
    return text, found


def _block(category: str, reason: str) -> InputVerdict:
    logger.warning("Input blocked (%s): %s", category, reason)
    return InputVerdict(allowed=False, text="", category=category, reason=reason)


def check_input(text: str) -> InputVerdict:
    """Run all input guardrails and return the verdict (never raises)."""
    text = normalise(text or "")

    if not text:
        return _block("empty", "Please enter a question.")
    if len(text) > MAX_INPUT_CHARS:
        return _block("too_long", f"Question is too long (max {MAX_INPUT_CHARS} characters).")
    if _looks_like_injection(text):
        return _block("injection", "This looks like an attempt to override my instructions, so I can't process it.")
    if any(p.search(text) for p in patterns.HARMFUL_INTENT):
        return _block("harmful", "I can't help with requests intended to cause harm.")
    if any(p.search(text) for p in patterns.SECRETS):
        return _block("secret", "Your message appears to contain a credential or secret. Remove it and ask again.")

    text, redacted = _redact_personal_data(text)
    if redacted:
        logger.info("Redacted personal data from input: %s", ", ".join(redacted))
    return InputVerdict(allowed=True, text=text, redacted=redacted)


def validate_input(text: str) -> str:
    """Chain step: return the sanitised question, or raise GuardrailViolation."""
    verdict = check_input(text)
    if not verdict.allowed:
        raise GuardrailViolation(verdict)
    return verdict.text
