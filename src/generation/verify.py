"""
Groundedness verification: audit a drafted answer against the documents it was written from and,
if it contains claims the documents do not support, rewrite it once with those claims removed.

Prompting alone does not stop a model from adding a plausible-sounding "ideal for..." or "more complex
than..." to a comparison; an independent check does.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel

from src.config import Settings, get_settings
from src.generation.formatting import clean_answer
from src.generation.prompts import NO_ANSWER

logger = logging.getLogger("rag.verify")

AUDIT_PROMPT = """You audit an answer for faithfulness to reference documents.

List every claim in the ANSWER that the DOCUMENTS do not state or clearly entail: outside knowledge, invented details, and evaluative or comparative judgements (ideal, simpler, more complex, a good choice, suitable for a scenario) that no document makes.
Ignore citation markers, formatting, and generic framing sentences that assert no facts.
Return an empty list if every claim is supported."""

REPAIR_PROMPT = """You correct answers so that they are strictly faithful to reference documents.

You are given DOCUMENTS, the QUESTION, an ANSWER and a list of UNSUPPORTED CLAIMS found in it. Rewrite the answer:
- remove or reword every unsupported claim so that only what the documents state remains;
- keep everything that is supported, and keep the answer's format: plain text, "- " bullets or numbered steps, and the [id] citations;
- add nothing new.
- if part of the question is supported, keep that part and add one plain sentence saying the documents do not cover the rest;
- use the refusal sentence only if nothing in the answer is supported by the documents: {no_answer}"""


class Audit(BaseModel):
    unsupported_claims: list[str]


@dataclass(frozen=True)
class Verification:
    answer: str
    status: str   # "passed" | "revised" | "unverified" (the check itself failed; the draft is returned as is)


class AnswerVerifier:
    """`auditor` maps {"context", "answer"} -> Audit; `rewriter` maps {..., "claims"} -> str."""

    def __init__(self, auditor: Runnable, rewriter: Runnable):
        self._auditor = auditor
        self._rewriter = rewriter

    def verify(self, question: str, context: str, answer: str) -> Verification:
        try:
            claims = [c for c in self._auditor.invoke({"context": context, "answer": answer}).unsupported_claims if c.strip()]
            if not claims:
                return Verification(answer, "passed")

            logger.info("Answer revised; unsupported claims: %s", claims)
            revised = clean_answer(self._rewriter.invoke({
                "context": context, "question": question, "answer": answer,
                "claims": "\n".join(f"- {c}" for c in claims),
            }))
            return Verification(revised, "revised") if revised else Verification(answer, "unverified")
        except Exception:
            logger.warning("Answer verification failed; returning the unverified draft", exc_info=True)
            return Verification(answer, "unverified")


def _build(settings: Settings) -> AnswerVerifier:
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        temperature=0,
        timeout=30,
        max_retries=1,
    )
    auditor = ChatPromptTemplate.from_messages([
        ("system", AUDIT_PROMPT),
        ("human", "DOCUMENTS:\n{context}\n\nANSWER:\n{answer}"),
    ]) | llm.with_structured_output(Audit, method="json_schema")

    rewriter = ChatPromptTemplate.from_messages([
        ("system", REPAIR_PROMPT.replace("{no_answer}", NO_ANSWER)),
        ("human", "DOCUMENTS:\n{context}\n\nQUESTION: {question}\n\nANSWER:\n{answer}\n\nUNSUPPORTED CLAIMS:\n{claims}"),
    ]) | llm | StrOutputParser()

    return AnswerVerifier(auditor, rewriter)


@lru_cache(maxsize=4)
def get_verifier(settings: Settings | None = None) -> AnswerVerifier | None:
    settings = settings or get_settings()
    if not settings.verify_answers:
        return None
    if not settings.openai_api_key:
        raise ValueError("VERIFY_ANSWERS=true requires OPENAI_API_KEY (or set VERIFY_ANSWERS=false).")
    return _build(settings)
