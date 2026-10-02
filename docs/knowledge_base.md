# Knowledge base

The chatbot answers only from the entries in `data/knowledge_base_v1/`. More (and better) entries mean better answers.

## What is in it

| Folder | Domain | Entry ids look like |
|---|---|---|
| `Cloud/AWS/` | AWS services | `aws-s3-001` |
| `DevOps/` | DevOps and SRE tooling and practice | `devops-helm-001` |
| `genai_fundamentals/` | LLMs, RAG, prompting, agents, safety | `rag-001` |
| `Workflows/` | Step-by-step how-tos for all domains | `wf-aws-deploy-container-on-aws-fargate-001` |
| `Course_projects/` | The course's own projects | `cp-aws-chatops-001` |
| `indexes/` | Generated lists of the entries above (do not edit by hand) | |

Run `python -m src.knowledge_base.workflow` for the current counts.

```
Experiments-/
├── data/knowledge_base_v1/
│   ├── Cloud/AWS/             # AWS services
│   ├── DevOps/                # DevOps and SRE tooling and practice
│   ├── genai_fundamentals/    # LLMs, RAG, prompting, agents, safety
│   ├── Workflows/             # step-by-step how-tos for all domains
│   ├── Course_projects/       # the course's own projects
│   └── indexes/               # generated lists of the entries; do not edit by hand
├── src/knowledge_base/        # loader.py, validator.py, workflow.py
├── kb_agents/                 # agentic workflow that grows the knowledge base
└── docs/                      # this file and entry_template.json
```

## Entry format

One JSON file per topic, one entry per file. Copy `docs/entry_template.json`. Required: `id`, `course`, `category`, `topic`,
`question`, `answer`. The rest (`subtopic`, `key_concepts`, `workflow`, `devops_application`, `official_evidence`,
`related_topics`, `course_context`) is strongly recommended; the workflow warns when it is missing.

Write like the existing entries: an `answer` of one to three precise sentences, no marketing wording, and an
`official_evidence` link to the vendor's own documentation. Entries written by the agents also carry a `provenance`
block (model, run, and the page they were written from).

## The workflow: keep the knowledge base healthy

```bash
python -m src.knowledge_base.workflow                # validate -> sync indexes -> rebuild the vector store
python -m src.knowledge_base.workflow --check        # CI mode: validate and verify the indexes; writes nothing
python -m src.knowledge_base.workflow --self-check   # does every entry's own question retrieve it (top 3)?
python -m src.knowledge_base.workflow --check-links  # do the documentation links respond? (needs network)
```

- **Validate**: schema and quality rules (id format, answer length, https links, duplicate ids/topics). Errors stop the run.
- **Indexes**: `indexes/*.json` are rebuilt from the entries, which are the source of truth.
- **Load into Chroma**: chunks and embeds every entry. The vector store is not in git; every teammate runs this once.
- **Self-check**: an entry that its own question cannot find has a weak question or overlaps another entry.

`pytest` runs the same checks on the real data (`tests/test_kb_data.py`), so a malformed entry fails the tests.

## Growing it with the agents

`kb_agents/` is an agentic workflow (LangGraph) that runs **separately from the chatbot**. Each domain is its own run:

```bash
python -m kb_agents run --domain aws    --concepts 30 --workflows 8
python -m kb_agents run --domain devops --concepts 25 --workflows 8
python -m kb_agents run --domain genai  --concepts 20 --workflows 8
python -m kb_agents merge --all --self-check        # after you have looked at the staged entries
```

For each topic:

```
plan (new topics only) -> research (fetch the official page) -> write -> review (fact-check) -> validate -> de-duplicate -> stage
                                                          ^_____ revise, up to twice _____|
```

- The **planner** proposes topics that the knowledge base does not already cover, each with an official documentation URL.
- The **researcher** fetches that page. If it cannot (404, no text, wrong page) the topic is **rejected**: nothing is written from memory.
- The **writer** may use only what the page says; the **reviewer** checks accuracy against the page (not completeness) and can send the draft back.
- Deterministic gates then check the schema and quality rules and reject near-duplicates of existing entries.
- Accepted entries land in `data/staging/<run-id>/` with a `report.json` explaining every rejection. **Nothing enters the knowledge
  base until you run `merge`**, which never overwrites an existing file.

Limits worth knowing: it needs `OPENAI_API_KEY`; runs share your token rate limit, so run domains one after another; yield
depends on the planner finding real documentation pages (topics without a stable page are rejected, not guessed); and the
result is only as good as the source page. A person should still skim what was staged before merging.

## Known issues

- `llm-001` and `rag-001` exist twice (in `fundamentals.json` and in their own files). The copy in `fundamentals.json` is used;
  the workflow warns about it. Remove one copy of each to clear the warning.
