from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from src.generation.chain import build_rag_pipeline
from src.generation.prompts import NO_ANSWER
from src.generation.verify import Audit, AnswerVerifier
from src.retrieval.retriever import get_retriever


def _verifier(claims, rewrite="Corrected answer [aws-s3-001].", audit_error=None, rewrite_error=None):
    calls = {"audit": [], "rewrite": []}

    def audit(payload):
        calls["audit"].append(payload)
        if audit_error:
            raise audit_error
        return Audit(unsupported_claims=claims)

    def rewriter(payload):
        calls["rewrite"].append(payload)
        if rewrite_error:
            raise rewrite_error
        return rewrite

    return AnswerVerifier(RunnableLambda(audit), RunnableLambda(rewriter)), calls


def test_a_fully_supported_answer_passes_untouched_without_a_rewrite():
    verifier, calls = _verifier([])
    result = verifier.verify("q", "ctx", "S3 stores objects [aws-s3-001].")
    assert (result.status, result.answer) == ("passed", "S3 stores objects [aws-s3-001].") and calls["rewrite"] == []


def test_unsupported_claims_trigger_one_rewrite_that_is_told_which_claims():
    verifier, calls = _verifier(["EKS is ideal for Kubernetes fans", "  "])
    result = verifier.verify("q", "ctx", "draft")

    assert result.status == "revised" and result.answer == "Corrected answer [aws-s3-001]."
    assert len(calls["rewrite"]) == 1 and calls["rewrite"][0]["claims"] == "- EKS is ideal for Kubernetes fans"
    assert calls["rewrite"][0]["answer"] == "draft" and calls["audit"][0]["context"] == "ctx"


def test_the_rewrite_is_stripped_of_markdown_like_any_other_answer():
    verifier, _ = _verifier(["x"], rewrite="**Bold** claim [aws-s3-001]")
    assert verifier.verify("q", "ctx", "draft").answer == "Bold claim [aws-s3-001]"


def test_a_failing_audit_never_blocks_the_answer():
    verifier, _ = _verifier([], audit_error=RuntimeError("judge down"))
    result = verifier.verify("q", "ctx", "draft")
    assert (result.status, result.answer) == ("unverified", "draft")


def test_a_failing_rewrite_keeps_the_draft_and_says_it_is_unverified():
    verifier, _ = _verifier(["bad claim"], rewrite_error=RuntimeError("rewriter down"))
    result = verifier.verify("q", "ctx", "draft")
    assert (result.status, result.answer) == ("unverified", "draft")


def test_an_empty_rewrite_keeps_the_draft():
    verifier, _ = _verifier(["bad claim"], rewrite="   ")
    assert verifier.verify("q", "ctx", "draft").status == "unverified"


# ---------- in the pipeline ----------

def _pipeline(fake_store, verifier, reply="Draft answer [aws-s3-001]."):
    retriever = get_retriever(k=2, min_score=-1, store=fake_store)
    llm = RunnableLambda(lambda _: AIMessage(content=reply))
    return build_rag_pipeline(llm, retriever, verifier)


def test_the_pipeline_returns_the_revised_answer_and_its_status(fake_store):
    docs = get_retriever(k=2, min_score=-1, store=fake_store).invoke("What is S3?")
    revised = f"Revised [{docs[0].metadata['id']}]"
    verifier, calls = _verifier(["unsupported"], rewrite=revised)

    out = _pipeline(fake_store, verifier).invoke("What is S3?")
    assert out["answer"] == revised and out["verification"] == "revised" and len(out["docs"]) == 2
    assert "<document id=" in calls["audit"][0]["context"]          # the auditor sees the same context the model saw


def test_a_refusal_is_not_audited(fake_store):
    verifier, calls = _verifier(["would never be asked"])
    out = _pipeline(fake_store, verifier, reply=NO_ANSWER).invoke("What is S3?")
    assert out["answer"] == NO_ANSWER and out["verification"] == "skipped" and calls["audit"] == []


def test_without_a_verifier_the_step_is_skipped(fake_store):
    out = _pipeline(fake_store, None).invoke("What is S3?")
    assert out["verification"] == "skipped"
