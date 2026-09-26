"""
The LangGraph workflow for one domain.

  plan ──► process_topic (one per proposal, run in parallel) ──► finalize
                │
                └─ research → write → review ─┬─ accept → assemble
                              ▲               ├─ revise ─┐ (up to N times)
                              └───────────────┘          └─ reject
"""

import math
import operator
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from kb_agents.agents import Agents
from kb_agents.domains import Domain
from kb_agents.models import Draft, Proposal
from kb_agents.research import Source
from kb_agents.staging import ExistingKB, build_entry, check_duplicate, entry_problems, relative_path, slug_of


@dataclass(frozen=True)
class RunConfig:
    domain: Domain
    n_concepts: int
    n_workflows: int
    run_id: str
    model: str
    max_revisions: int = 2
    allow_ungrounded: bool = False
    oversample: float = 1.4          # propose extra topics: some will be rejected


class TopicState(TypedDict, total=False):
    proposal: dict
    source: str
    grounded: bool
    note: str
    draft: dict
    issues: list[str]
    revisions: int
    verdict: str
    outcome: dict


class RunState(TypedDict, total=False):
    proposals: list[dict]
    results: Annotated[list[dict], operator.add]
    accepted: list[dict]
    rejected: list[dict]


def _outcome(status: str, reason: str, proposal: Proposal, *, entry: dict | None = None, grounded: bool = False, revisions: int = 0) -> dict:
    return {"status": status, "reason": reason, "kind": proposal.kind, "topic": proposal.topic, "slug": proposal.slug,
            "path": "", "entry": entry, "grounded": grounded, "revisions": revisions}


def build_graph(agents: Agents, fetch: Callable[[str, str], Source], existing: ExistingKB, cfg: RunConfig,
                nearest: Callable[[str], tuple[float, str] | None] | None = None, log: Callable[[str], None] = print):
    domain = cfg.domain

    # ---- one topic: research -> write -> review (-> revise) -> assemble
    def research(state: TopicState) -> dict:
        proposal = Proposal(**state["proposal"])
        source = fetch(proposal.source_url, proposal.topic)
        return {"source": source.text, "grounded": source.ok, "note": source.note}

    def route_source(state: TopicState) -> str:
        return "write" if state["grounded"] or cfg.allow_ungrounded else "reject_source"

    def reject_source(state: TopicState) -> dict:
        proposal = Proposal(**state["proposal"])
        return {"outcome": _outcome("rejected", f"source unavailable: {state['note']}", proposal)}

    def write(state: TopicState) -> dict:
        draft = agents.write(domain, Proposal(**state["proposal"]), state["source"], state["grounded"], state.get("issues", []))
        return {"draft": draft.model_dump()}

    def review(state: TopicState) -> dict:
        result = agents.review(Proposal(**state["proposal"]), state["source"], state["grounded"], Draft(**state["draft"]))
        return {"verdict": result.verdict, "issues": result.issues}

    def route_review(state: TopicState) -> str:
        if state["verdict"] == "accept":
            return "assemble"
        if state["verdict"] != "reject" and state.get("revisions", 0) < cfg.max_revisions:
            return "prepare_revision"
        return "reject_review"

    def prepare_revision(state: TopicState) -> dict:
        return {"revisions": state.get("revisions", 0) + 1}

    def reject_review(state: TopicState) -> dict:
        proposal = Proposal(**state["proposal"])
        issues = "; ".join(state.get("issues", []))[:300]
        return {"outcome": _outcome("rejected", f"review: {state['verdict']} - {issues}", proposal,
                                    grounded=state["grounded"], revisions=state.get("revisions", 0))}

    def assemble(state: TopicState) -> dict:
        proposal = Proposal(**state["proposal"])
        entry = build_entry(domain, proposal, Draft(**state["draft"]), grounded=state["grounded"], model=cfg.model, run_id=cfg.run_id)
        problems = entry_problems(entry, slug_of(domain, proposal))
        if problems:
            return {"outcome": _outcome("rejected", "validation: " + "; ".join(problems), proposal,
                                        grounded=state["grounded"], revisions=state.get("revisions", 0))}
        out = _outcome("accepted", "passed review and validation", proposal, entry=entry,
                       grounded=state["grounded"], revisions=state.get("revisions", 0))
        out["path"] = relative_path(domain, proposal)
        return {"outcome": out}

    topic = StateGraph(TopicState)
    for name, fn in [("research", research), ("reject_source", reject_source), ("write", write), ("review", review),
                     ("prepare_revision", prepare_revision), ("reject_review", reject_review), ("assemble", assemble)]:
        topic.add_node(name, fn)
    topic.add_edge(START, "research")
    topic.add_conditional_edges("research", route_source, ["write", "reject_source"])
    topic.add_edge("write", "review")
    topic.add_conditional_edges("review", route_review, ["assemble", "prepare_revision", "reject_review"])
    topic.add_edge("prepare_revision", "write")
    for name in ("reject_source", "reject_review", "assemble"):
        topic.add_edge(name, END)
    topic_graph = topic.compile()

    # ---- the domain run: plan -> fan out -> finalize
    def plan(state: RunState) -> dict:
        want_c, want_w = math.ceil(cfg.n_concepts * cfg.oversample), math.ceil(cfg.n_workflows * cfg.oversample)
        seen_topics, seen_slugs, kept = set(existing.topics), set(), []
        for proposal in agents.plan(domain, existing.topic_names, want_c, want_w):
            key = proposal.topic.strip().lower()
            slug = slug_of(domain, proposal)
            if key in seen_topics or slug in seen_slugs:
                continue
            seen_topics.add(key)
            seen_slugs.add(slug)
            kept.append(proposal.model_dump())
        log(f"[{domain.key}] planner proposed {len(kept)} new topics")
        return {"proposals": kept}

    def fan_out(state: RunState):
        return [Send("process_topic", {"proposal": p}) for p in state["proposals"]] or END

    def process_topic(payload: dict) -> dict:
        try:
            result = topic_graph.invoke({"proposal": payload["proposal"], "revisions": 0, "issues": []})["outcome"]
        except Exception as error:      # a failing topic (rate limit, bad response) is rejected; the run carries on
            proposal = Proposal(**payload["proposal"])
            result = _outcome("rejected", f"error: {type(error).__name__}: {str(error)[:120]}", proposal)
        log(f"[{domain.key}] {result['status']:8} {result['topic']}" + ("" if result["status"] == "accepted" else f"  ({result['reason'][:110]})"))
        return {"results": [result]}

    def finalize(state: RunState) -> dict:
        accepted, rejected = [], []
        batch_topics: set[str] = set()
        quota = {"concept": cfg.n_concepts, "workflow": cfg.n_workflows}
        for item in sorted(state.get("results", []), key=lambda r: (r["status"] != "accepted", r["kind"], r["topic"])):
            if item["status"] != "accepted":
                rejected.append(item)
                continue
            why = check_duplicate(item["entry"], existing, batch_topics, nearest)
            if why is None and quota[item["kind"]] <= 0:
                why = "over the requested count"
            if why:
                rejected.append({**item, "status": "rejected", "reason": why, "entry": None})
                continue
            quota[item["kind"]] -= 1
            batch_topics.add(item["entry"]["topic"].strip().lower())
            accepted.append(item)
        return {"accepted": accepted, "rejected": rejected}

    run = StateGraph(RunState)
    run.add_node("plan", plan)
    run.add_node("process_topic", process_topic)
    run.add_node("finalize", finalize)
    run.add_edge(START, "plan")
    run.add_conditional_edges("plan", fan_out, ["process_topic", END])
    run.add_edge("process_topic", "finalize")
    run.add_edge("finalize", END)
    return run.compile()
