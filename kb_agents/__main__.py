"""
    python -m kb_agents run --domain aws|devops|genai [--concepts 20] [--workflows 6]
    python -m kb_agents merge [--all | RUN_ID ...] [--self-check]

`run` stages new entries under data/staging/<run-id>/ and touches nothing else. Run the domains separately
(even at the same time, in different terminals). `merge` copies staged entries into the knowledge base and then
runs the knowledge-base workflow: validate, sync indexes, load into Chroma.
"""

import argparse
import json
import sys
import threading
from datetime import datetime
from pathlib import Path

from kb_agents.domains import DOMAINS
from src.config import get_settings

_print_lock = threading.Lock()


def log(message: str) -> None:
    with _print_lock:
        print(message, flush=True)


def _nearest_fn():
    """Similarity of a question to what the knowledge base already holds (local embeddings; no LLM)."""
    try:
        from src.retrieval.retriever import search

        search("warm-up", k=1, min_score=-1)          # fails early if there is no vector store yet

        def nearest(question: str):
            hits = search(question, k=1, min_score=-1)
            return (hits[0].score, hits[0].document.metadata["id"]) if hits else None

        return nearest
    except Exception as error:      # first-ever run, before the vector store exists
        log(f"note: semantic duplicate check disabled ({type(error).__name__}: {error})")
        return None


def cmd_run(args) -> int:
    from kb_agents.agents import LLMAgents
    from kb_agents.graph import RunConfig, build_graph
    from kb_agents.research import fetch_source
    from kb_agents.staging import existing_state, write_stage

    settings = get_settings()
    domain = DOMAINS[args.domain]
    run_id = args.run_id or f"{datetime.now():%Y%m%d-%H%M%S}-{domain.key}"
    existing = existing_state(settings.data_dir)
    agents = LLMAgents(settings)

    if args.plan_only:
        for p in agents.plan(domain, existing.topic_names, args.concepts, args.workflows):
            print(f"{p.kind:9} {p.topic}  <{p.source_url}>")
        return 0

    cfg = RunConfig(domain, args.concepts, args.workflows, run_id, settings.llm_model, allow_ungrounded=args.allow_ungrounded)
    log(f"[{domain.key}] run {run_id}: {args.concepts} concepts + {args.workflows} workflows, {len(existing.ids)} existing entries")
    graph = build_graph(agents, fetch_source, existing, cfg, nearest=_nearest_fn(), log=log)
    state = graph.invoke({}, config={"max_concurrency": args.concurrency})

    accepted, rejected = state.get("accepted", []), state.get("rejected", [])
    stage_dir = settings.data_dir.parent / "staging" / run_id
    write_stage(stage_dir, [(a["path"], a["entry"]) for a in accepted], {
        "run": run_id, "domain": domain.key, "model": settings.llm_model,
        "accepted": [{k: a[k] for k in ("topic", "kind", "path", "grounded", "revisions")} for a in accepted],
        "rejected": [{k: r[k] for k in ("topic", "kind", "reason")} for r in rejected],
    })
    log(f"\n[{domain.key}] accepted {len(accepted)} ({sum(a['kind'] == 'concept' for a in accepted)} concepts, "
        f"{sum(a['kind'] == 'workflow' for a in accepted)} workflows), rejected {len(rejected)} -> {stage_dir}")
    return 0


def cmd_merge(args) -> int:
    from kb_agents.staging import merge_stage
    from src.knowledge_base import workflow

    settings = get_settings()
    staging = settings.data_dir.parent / "staging"
    runs = [staging / r for r in args.runs] if args.runs else sorted(
        d for d in staging.glob("*") if (d / "entries").is_dir() and not (d / "merged.json").exists())
    if not runs:
        print("Nothing staged to merge.")
        return 0

    for stage in runs:
        result = merge_stage(stage, settings.data_dir)
        print(f"{stage.name}: merged {len(result.copied)} entries" + (f", skipped {len(result.skipped)} that already exist" if result.skipped else ""))

    return workflow.main(["--self-check"] if args.self_check else [])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="kb_agents", description="Agentic workflow that grows the knowledge base.")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="plan, research, write, review and stage new entries for one domain")
    run.add_argument("--domain", required=True, choices=sorted(DOMAINS))
    run.add_argument("--concepts", type=int, default=20, help="concept entries to add")
    run.add_argument("--workflows", type=int, default=6, help="step-by-step workflow entries to add")
    run.add_argument("--concurrency", type=int, default=2, help="topics processed in parallel")
    run.add_argument("--allow-ungrounded", action="store_true", help="also accept topics whose documentation page could not be fetched")
    run.add_argument("--plan-only", action="store_true", help="print the planner's proposals and stop")
    run.add_argument("--run-id")
    run.set_defaults(func=cmd_run)

    merge = sub.add_parser("merge", help="merge staged entries into the knowledge base and load them into Chroma")
    merge.add_argument("runs", nargs="*", help="run ids (default: every staged run not yet merged)")
    merge.add_argument("--self-check", action="store_true")
    merge.set_defaults(func=cmd_merge)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
