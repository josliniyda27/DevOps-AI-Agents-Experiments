import json

import httpx
import pytest

from kb_agents.domains import DOMAINS
from kb_agents.graph import RunConfig, build_graph
from kb_agents.models import Draft, Proposal, Review
from kb_agents.research import Source, fetch_source, html_to_text, is_relevant
from kb_agents.staging import (
    ExistingKB, build_entry, check_duplicate, dump_entry, entry_problems, merge_stage, relative_path, slug_of, write_stage,
)
from src.knowledge_base import KnowledgeBaseLoader

AWS = DOMAINS["aws"]


def proposal(slug="cloudfront", topic="Amazon CloudFront", kind="concept", **over) -> Proposal:
    base = dict(kind=kind, slug=slug, topic=topic, subtopic="Content delivery network", question=f"What is {topic}?",
                source_url="https://docs.example.com/cf", category="AWS Cloud", module="AWS Networking", group="Networking")
    return Proposal(**(base | over))


def draft(**over) -> Draft:
    base = dict(subtopic="Content delivery network", answer="Amazon CloudFront is a content delivery service that serves content from edge locations.",
                key_concepts=["Distributions", "Edge locations", "Origins"], workflow=["Create a distribution", "Set an origin", "Deploy it"],
                devops_application="Teams put it in front of web apps.", related_topics=["S3", "Route 53", "WAF"], usage="Used to speed up sites.")
    return Draft(**(base | over))


# ---------- researcher ----------

def test_html_becomes_readable_text_without_chrome():
    html = "<html><nav>Menu Home</nav><script>var x=1</script><h1>Title</h1><p>First   paragraph.</p><footer>Legal</footer><li>Item</li></html>"
    text = html_to_text(html)
    assert "Title" in text and "First paragraph." in text and "Item" in text
    assert "Menu" not in text and "var x" not in text and "Legal" not in text


def test_relevance_ignores_generic_words():
    assert is_relevant("CloudFront serves content", "Amazon CloudFront")
    assert not is_relevant("A page about something else entirely", "Amazon CloudFront")
    assert is_relevant("anything", "AWS Service")           # only generic words: nothing to check


def test_one_shared_word_is_not_enough_to_count_as_about_the_topic():
    assert is_relevant("Agent memory lets an agent remember earlier turns.", "Agent Memory")
    assert is_relevant("Nearest-neighbour indexes speed up approximate search.", "Approximate Nearest-Neighbour Indexes")
    assert not is_relevant("Build agents that call tools and use vector search.", "Agent Memory")


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _page(text, content_type="text/html"):
    return httpx.Response(200, text=f"<html><body><p>{text}</p></body></html>", headers={"content-type": content_type})


@pytest.mark.parametrize("response, note", [
    (httpx.Response(404), "HTTP 404"),
    (_page("CloudFront is a CDN. " * 5), "too little text"),
    (_page("Something unrelated to the subject at all. " * 30), "does not mention the topic"),
    (_page("CloudFront is a CDN. " * 60, "application/pdf"), "not an HTML page"),
])
def test_unusable_pages_are_reported_with_a_reason(response, note):
    source = fetch_source("https://docs.example.com/cf", "Amazon CloudFront", _client(lambda r: response))
    assert not source.ok and note in source.note


def test_a_good_page_is_returned_trimmed_and_marked_ok():
    source = fetch_source("https://docs.example.com/cf", "Amazon CloudFront", _client(lambda r: _page("CloudFront delivers content quickly. " * 400)))
    assert source.ok and 500 < len(source.text) <= 5000


def test_plain_http_and_unreachable_hosts_are_not_fetched():
    assert fetch_source("http://insecure.example.com", "x").note == "not an https url"

    def boom(request):
        raise httpx.ConnectError("down")
    assert "unreachable" in fetch_source("https://docs.example.com/cf", "x", _client(boom)).note


# ---------- staging ----------

def test_slugs_lose_redundant_vendor_prefixes_so_ids_read_naturally():
    assert [slug_of(AWS, proposal(slug=s)) for s in ("aws-cloudfront", "amazon-s3", "aws-amazon-athena", "cloudfront", "aws")] == \
        ["cloudfront", "s3", "athena", "cloudfront", "aws"]


def test_concept_entries_follow_the_house_conventions():
    e = build_entry(AWS, proposal(slug="aws-cloudfront"), draft(), grounded=True, model="gpt-4o", run_id="r1")
    assert e["id"] == "aws-cloudfront-001" and e["category"] == "AWS Cloud" and e["group"] == "Networking"
    assert e["course_context"]["module"] == "AWS Networking" and e["official_evidence"][0]["source_type"] == "official_documentation"
    assert e["provenance"] == {"method": "agentic-workflow", "model": "gpt-4o", "grounded": True, "source_url": "https://docs.example.com/cf", "run": "r1"}
    assert relative_path(AWS, proposal(slug="aws-cloudfront")) == "Cloud/AWS/cloudfront.json"


def test_workflow_entries_get_their_own_id_category_and_folder():
    p = proposal(slug="deploy-static-site", topic="Host a Static Site", kind="workflow")
    e = build_entry(AWS, p, draft(), grounded=True, model="m", run_id="r")
    assert e["id"] == "wf-aws-deploy-static-site-001" and e["category"] == "AWS Workflows" and "group" not in e
    assert e["course_context"]["module"] == "Workflows" and relative_path(AWS, p) == "Workflows/aws_deploy_static_site.json"


def test_unknown_categories_modules_and_groups_fall_back_to_safe_values():
    e = build_entry(AWS, proposal(category="Made Up", module="Nope", group="Nope"), draft(), grounded=True, model="m", run_id="r")
    assert (e["category"], e["course_context"]["module"]) == ("AWS Cloud", AWS.modules[0]) and "group" not in e


def test_a_subtopic_that_repeats_the_topic_name_is_replaced():
    e = build_entry(AWS, proposal(), draft(subtopic="amazon cloudfront"), grounded=True, model="m", run_id="r")
    assert e["subtopic"] == "Content delivery network"


def test_when_the_model_only_repeats_the_topic_the_subtopic_falls_back_to_the_category_or_workflow_label():
    repeat = draft(subtopic="Amazon CloudFront")
    concept = build_entry(AWS, proposal(subtopic="amazon cloudfront"), repeat, grounded=True, model="m", run_id="r")
    assert concept["subtopic"] == "AWS Cloud" and entry_problems(concept, "cloudfront") == []

    how_to = build_entry(AWS, proposal(kind="workflow", topic="Deploy", subtopic="deploy"), draft(subtopic="Deploy"), grounded=True, model="m", run_id="r")
    assert how_to["subtopic"] == "Step-by-step workflow"


def _built(**over):
    return build_entry(AWS, proposal(), draft(**over), grounded=True, model="m", run_id="r")


def test_a_well_formed_entry_has_no_problems():
    assert entry_problems(_built(), "cloudfront") == []


@pytest.mark.parametrize("over, expected", [
    ({"answer": "Too short."}, "shorter than"),
    ({"answer": "x" * 500}, "longer than"),
    ({"key_concepts": ["Only one"]}, "fewer than 3 key concepts"),
    ({"workflow": ["One", "Two"]}, "fewer than 3 workflow steps"),
])
def test_entries_that_break_the_rules_are_rejected(over, expected):
    assert any(expected in p for p in entry_problems(_built(**over), "cloudfront"))


@pytest.mark.parametrize("over", [
    {"answer": "Agent Memory is not mentioned in the provided source documentation."},
    {"answer": "It is described well enough here, but the documentation does not say how to start."},
    {"workflow": ["Do one thing", "According to the source, wait", "Do another thing"]},
    {"devops_application": "No information is given about how teams use it in the source."},
])
def test_entries_that_talk_about_their_source_are_rejected(over):
    assert any("talks about its source" in p for p in entry_problems(_built(**over), "cloudfront"))


def test_a_bad_slug_is_rejected():
    assert any("slug" in p for p in entry_problems(_built(), "Bad Slug"))


def test_duplicates_are_caught_by_id_topic_batch_and_similarity():
    e = _built()
    existing = ExistingKB(ids={"aws-cloudfront-001"}, topics={"s3"})
    assert "already exists" in check_duplicate(e, existing, set())
    assert "already in the knowledge base" in check_duplicate(e, ExistingKB(topics={"amazon cloudfront"}), set())
    assert "same topic" in check_duplicate(e, ExistingKB(), {"amazon cloudfront"})
    assert "near-duplicate of aws-s3-001" in check_duplicate(e, ExistingKB(), set(), nearest=lambda q: (0.93, "aws-s3-001"))
    assert check_duplicate(e, ExistingKB(), set(), nearest=lambda q: (0.60, "aws-s3-001")) is None


def test_written_entries_load_back_through_the_real_loader(tmp_path):
    e = _built()
    write_stage(tmp_path / "stage", [("Cloud/AWS/cloudfront.json", e)], {"run": "r"})
    loaded = KnowledgeBaseLoader(tmp_path / "stage" / "entries").load_entries()
    assert loaded.invalid == [] and loaded.entries[0]["id"] == "aws-cloudfront-001"
    assert '"key_concepts": ["Distributions", "Edge locations", "Origins"]' in dump_entry(e)        # house style: short lists inline


def test_merging_copies_new_entries_and_never_overwrites_existing_files(tmp_path):
    e = _built()
    stage, kb = tmp_path / "stage", tmp_path / "kb"
    write_stage(stage, [("Cloud/AWS/cloudfront.json", e), ("Cloud/AWS/other.json", e)], {"run": "r"})
    (kb / "Cloud/AWS").mkdir(parents=True)
    (kb / "Cloud/AWS/other.json").write_text("HAND-WRITTEN")

    result = merge_stage(stage, kb)
    assert result.copied == ["Cloud/AWS/cloudfront.json"] and result.skipped == ["Cloud/AWS/other.json"]
    assert (kb / "Cloud/AWS/other.json").read_text() == "HAND-WRITTEN"
    assert (stage / "merged.json").exists()


# ---------- the graph ----------

class FakeAgents:
    """Scripted agents. `verdicts[topic]` is the list of review verdicts, one per attempt."""

    def __init__(self, proposals, verdicts=None, fail_on=()):
        self.proposals, self.verdicts, self.fail_on = proposals, verdicts or {}, set(fail_on)
        self.writes, self.attempt = [], {}

    def plan(self, domain, existing_topics, n_concepts, n_workflows):
        self.planned_for = (n_concepts, n_workflows, list(existing_topics))
        return self.proposals

    def write(self, domain, p, source, grounded, issues):
        if p.topic in self.fail_on:
            raise RuntimeError("model exploded")
        self.writes.append((p.topic, list(issues), source))
        return draft()

    def review(self, p, source, grounded, d):
        n = self.attempt[p.topic] = self.attempt.get(p.topic, -1) + 1
        script = self.verdicts.get(p.topic, ["accept"])
        verdict = script[min(n, len(script) - 1)]
        return Review(verdict=verdict, issues=[] if verdict == "accept" else [f"problem {n}"])


def fetch_ok(url, topic):
    return Source("Reference text about " + topic, True, "")


def fetch_fail(url, topic):
    return Source("", False, "HTTP 404")


def run(agents, *, n_concepts=5, n_workflows=5, fetch=fetch_ok, existing=None, allow_ungrounded=False, nearest=None, revisions=2):
    cfg = RunConfig(AWS, n_concepts, n_workflows, "run1", "gpt-4o", max_revisions=revisions, allow_ungrounded=allow_ungrounded, oversample=1.0)
    return build_graph(agents, fetch, existing or ExistingKB(), cfg, nearest=nearest, log=lambda m: None).invoke({}, config={"max_concurrency": 2})


def topics(items):
    return sorted(i["topic"] for i in items)


def test_the_happy_path_accepts_reviewed_entries_with_their_paths():
    state = run(FakeAgents([proposal("a", "Alpha"), proposal("b", "Beta", kind="workflow")]))
    assert topics(state["accepted"]) == ["Alpha", "Beta"] and state["rejected"] == []
    assert {a["path"] for a in state["accepted"]} == {"Cloud/AWS/a.json", "Workflows/aws_b.json"}
    assert all(a["entry"]["provenance"]["grounded"] for a in state["accepted"])


def test_a_draft_that_fails_review_is_revised_with_the_reviewers_notes_then_accepted():
    agents = FakeAgents([proposal("a", "Alpha")], verdicts={"Alpha": ["revise", "accept"]})
    state = run(agents)
    assert topics(state["accepted"]) == ["Alpha"] and state["accepted"][0]["revisions"] == 1
    assert agents.writes[0][1] == [] and agents.writes[1][1] == ["problem 0"]          # second draft receives the issues


def test_a_draft_that_never_passes_is_rejected_after_the_revision_limit():
    agents = FakeAgents([proposal("a", "Alpha")], verdicts={"Alpha": ["revise"]})
    state = run(agents, revisions=2)
    assert state["accepted"] == [] and "review: revise" in state["rejected"][0]["reason"] and len(agents.writes) == 3


def test_an_outright_reject_verdict_is_final():
    agents = FakeAgents([proposal("a", "Alpha")], verdicts={"Alpha": ["reject"]})
    assert len(agents.writes) == 0 and run(agents)["rejected"][0]["reason"].startswith("review: reject") and len(agents.writes) == 1


def test_topics_without_a_fetched_source_are_rejected_unless_allowed():
    agents = FakeAgents([proposal("a", "Alpha")])
    assert "source unavailable: HTTP 404" in run(agents, fetch=fetch_fail)["rejected"][0]["reason"] and agents.writes == []

    state = run(FakeAgents([proposal("a", "Alpha")]), fetch=fetch_fail, allow_ungrounded=True)
    assert topics(state["accepted"]) == ["Alpha"] and state["accepted"][0]["entry"]["provenance"]["grounded"] is False


def test_one_failing_topic_does_not_sink_the_run():
    agents = FakeAgents([proposal("a", "Alpha"), proposal("b", "Beta")], fail_on={"Alpha"})
    state = run(agents)
    assert topics(state["accepted"]) == ["Beta"] and "error: RuntimeError" in state["rejected"][0]["reason"]


def test_the_planner_sees_existing_topics_and_proposals_that_repeat_them_are_dropped():
    agents = FakeAgents([proposal("s3", "S3"), proposal("a", "Alpha"), proposal("a2", "alpha"), proposal("b", "Beta")])
    state = run(agents, existing=ExistingKB(ids=set(), topics={"s3"}, topic_names=["S3"]))
    assert topics(state["accepted"]) == ["Alpha", "Beta"] and agents.planned_for[2] == ["S3"]


def test_results_are_capped_at_the_requested_counts_and_duplicates_removed():
    agents = FakeAgents([proposal(f"c{i}", f"Concept {i}") for i in range(4)] + [proposal("w", "Work", kind="workflow")])
    state = run(agents, n_concepts=2, n_workflows=1)
    assert len([a for a in state["accepted"] if a["kind"] == "concept"]) == 2
    assert {r["reason"] for r in state["rejected"]} == {"over the requested count"}

    near = run(FakeAgents([proposal("a", "Alpha")]), nearest=lambda q: (0.95, "aws-s3-001"))
    assert near["accepted"] == [] and "near-duplicate of aws-s3-001" in near["rejected"][0]["reason"]


def test_an_empty_plan_is_an_empty_result():
    assert run(FakeAgents([])).get("accepted", []) == []
