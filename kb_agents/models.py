"""Structured outputs of the agents. Every field is required, which keeps them compatible with strict JSON schemas."""

from typing import Literal

from pydantic import BaseModel


class Proposal(BaseModel):
    kind: Literal["concept", "workflow"]   # a concept explains a topic; a workflow is a step-by-step how-to
    slug: str                              # short id fragment, e.g. "cloudfront" or "static-site-s3"
    topic: str                             # canonical name, e.g. "Amazon CloudFront"
    subtopic: str                          # a few words on what it is
    question: str                          # the question the entry answers
    source_url: str                        # https page in the official documentation
    category: str
    module: str
    group: str                             # service group for AWS entries, otherwise an empty string


class Plan(BaseModel):
    proposals: list[Proposal]


class Draft(BaseModel):
    subtopic: str
    answer: str
    key_concepts: list[str]
    workflow: list[str]
    devops_application: str
    related_topics: list[str]
    usage: str                             # one sentence on where teams use it (goes to course_context.usage)


class Review(BaseModel):
    verdict: Literal["accept", "revise", "reject"]
    issues: list[str]
