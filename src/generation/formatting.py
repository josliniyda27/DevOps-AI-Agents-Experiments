"""Deterministic clean-up of the model's reply, so the UI only ever receives plain text."""

import re

from src.generation.prompts import SUMMARY_MARKER

_FENCE = re.compile(r"```[a-zA-Z0-9_-]*\n?|```")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_BOLD_ITALIC = re.compile(r"(\*\*|__)(.+?)\1|(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_STAR_BULLET = re.compile(r"^(\s*)[*•]\s+", re.MULTILINE)


def clean_answer(text: str) -> str:
    """Strip markdown emphasis, headings and code fences; normalise bullets and blank lines."""
    text = _FENCE.sub("", text)
    text = _HEADING.sub("", text)
    text = _STAR_BULLET.sub(r"\1- ", text)                       # "* item" -> "- item" (before emphasis is stripped)
    text = _BOLD_ITALIC.sub(lambda m: m.group(2) or m.group(3), text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def split_summary(text: str) -> tuple[str, list[str]]:
    """
    Split a reply into (answer, summary lines) at the knowledge-summary marker.
    A reply without the marker (a refusal, or a model that skipped it) has no summary.
    """
    answer, marker, summary = text.partition(SUMMARY_MARKER)
    if not marker:
        return text.strip(), []
    lines = [re.sub(r"^\s*[-*]\s*", "", line).strip() for line in summary.splitlines()]
    return answer.strip(), [line for line in lines if line]
