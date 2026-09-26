import logging
from operator import itemgetter

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable, RunnableBranch, RunnableLambda, RunnablePassthrough

from src.generation.condense import Condenser, get_condenser, prepare_history
from src.generation.context_builder import format_docs_to_xml
from src.generation.formatting import clean_answer, split_summary
from src.generation.llm import get_llm
from src.generation.prompts import NO_ANSWER, SYSTEM_PROMPT, rag_prompt
from src.generation.verify import AnswerVerifier, get_verifier
from src.guardrails.input_guards import check_input, validate_input
from src.guardrails.output_guards import validate_output
from src.retrieval.retriever import get_retriever

logger = logging.getLogger("rag.chain")


def build_rag_pipeline(
    llm: BaseChatModel | Runnable | None = None,
    retriever: Runnable | None = None,
    verifier: AnswerVerifier | None = None,
    condenser: Condenser | None = None,
) -> Runnable:
    """
    question (str) or {"question": str, "history": [{"role", "content"}, ...]}
        -> {"question", "standalone_question", "docs", "answer", "knowledge_summary", "verification"}

    1. Input guardrail   - raises GuardrailViolation if the question is blocked
    1b. Memory           - with conversation history, a follow-up is rewritten into a standalone question
    2. Retrieval         - vector search, chunks merged into entries, LLM re-ranking
    3. Grounding gate    - nothing relevant retrieved -> refuse without calling the LLM
    4. Generation        - system prompt + context + LLM
    5. Verification      - audit the draft against the documents; rewrite it if it makes unsupported claims
    6. Output guardrail  - redact secrets, block prompt leaks, drop fabricated citations

    `docs` are the entries the model was given (with relevance metadata); `answer` is the final reply and
    `knowledge_summary` the model's overview (list of lines) of what those documents contain;
    `verification` is "passed", "revised", "unverified" or "skipped".
    `llm`, `retriever` and `verifier` default to the configured ones; pass your own to test or swap them.
    """
    retriever = retriever or get_retriever()
    llm = llm or get_llm()
    verifier = verifier or get_verifier()
    condenser = condenser or get_condenser()

    def prepare(request: str | dict) -> dict:
        payload = {"question": request, "history": []} if isinstance(request, str) else request
        question = validate_input(payload["question"])                    # raises GuardrailViolation
        standalone = question

        history = prepare_history(payload.get("history") or [])
        if history:
            try:
                candidate = condenser.condense(question, history)
            except Exception:
                logger.warning("Could not rewrite the follow-up; using it as written", exc_info=True)
                candidate = question
            if candidate != question:
                verdict = check_input(candidate)                          # the rewrite is checked like any question
                standalone = verdict.text if verdict.allowed else question

        return {"question": question, "standalone_question": standalone}

    generate = (
        RunnableLambda(lambda state: {"context": format_docs_to_xml(state["docs"]), "question": state["standalone_question"]})
        | rag_prompt
        | llm
        | StrOutputParser()
        | RunnableLambda(clean_answer)
    )

    answer = RunnableBranch(
        (lambda state: not state["docs"], RunnableLambda(lambda state: NO_ANSWER)),
        generate,
    )

    def verify(state: dict) -> dict:
        if verifier is None or not state["docs"] or state["answer"] == NO_ANSWER:
            return {**state, "verification": "skipped"}
        result = verifier.verify(state["standalone_question"], format_docs_to_xml(state["docs"]), state["answer"])
        return {**state, "answer": result.answer, "verification": result.status}

    def guard_output(state: dict) -> dict:
        allowed_ids = {doc.metadata["id"] for doc in state["docs"]}
        guarded = validate_output(state["answer"], allowed_ids, SYSTEM_PROMPT, allowed_phrases=[NO_ANSWER])
        answer, summary = split_summary(guarded)            # both parts have been through the guardrails
        return {**state, "answer": answer, "knowledge_summary": summary}

    return (
        RunnableLambda(prepare).with_config(run_name="input_guardrail_and_memory")
        | RunnablePassthrough.assign(docs=lambda state: retriever.invoke(state["standalone_question"]))
        | RunnablePassthrough.assign(answer=answer)
        | RunnableLambda(verify).with_config(run_name="verify_grounding")
        | RunnableLambda(guard_output).with_config(run_name="output_guardrail")
    )


def build_rag_chain(
    llm: BaseChatModel | Runnable | None = None,
    retriever: Runnable | None = None,
    verifier: AnswerVerifier | None = None,
    condenser: Condenser | None = None,
) -> Runnable:
    """question (str) -> answer (str). Same steps as build_rag_pipeline, returning only the answer."""
    return build_rag_pipeline(llm, retriever, verifier, condenser) | itemgetter("answer")
