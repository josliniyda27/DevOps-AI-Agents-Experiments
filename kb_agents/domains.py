"""The knowledge domains the workflow can grow, and the conventions each one follows."""

from dataclasses import dataclass

WORKFLOWS_FOLDER = "Workflows"


@dataclass(frozen=True)
class Domain:
    key: str                       # name on the command line
    label: str
    description: str               # what the planner should cover
    concept_folder: str            # under the data directory
    categories: tuple[str, ...]    # allowed `category` values for concept entries
    id_prefix: str                 # prefix of concept ids, e.g. "aws-"
    modules: tuple[str, ...]       # allowed course_context.module values
    groups: tuple[str, ...]        # service groups used by the index (AWS only)
    workflow_category: str
    sources: str                   # which official documentation to cite


DOMAINS: dict[str, Domain] = {
    "aws": Domain(
        key="aws",
        label="AWS Cloud",
        description="AWS services and the practices around them that a DevOps or platform engineer uses: compute, storage, "
                    "networking, security and identity, databases, messaging, serverless, containers, developer tools, "
                    "monitoring and governance, and cost management.",
        concept_folder="Cloud/AWS",
        categories=("AWS Cloud",),
        id_prefix="aws-",
        modules=("AWS Basics", "AWS Networking", "AWS Security", "AWS Databases", "AWS Analytics", "AWS Messaging",
                 "AWS Containers", "AWS Developer Tools", "AWS Operations", "AWS AI"),
        groups=("Compute", "Storage", "Networking", "Security", "Databases", "Analytics", "Messaging", "Containers",
                "Serverless", "Monitoring", "DevTools", "AI", "Management"),
        workflow_category="AWS Workflows",
        sources="the official AWS documentation on docs.aws.amazon.com (prefer the service's 'What is ...' or Welcome page)",
    ),
    "devops": Domain(
        key="devops",
        label="DevOps",
        description="DevOps and SRE practice and tooling: source control and branching, CI/CD, containers and Kubernetes, "
                    "infrastructure as code, configuration management, GitOps, observability, deployment strategies, "
                    "DevSecOps, reliability engineering and incident management.",
        concept_folder="DevOps",
        categories=("DevOps",),
        id_prefix="devops-",
        modules=("DevOps", "CI/CD", "Containers and Kubernetes", "Infrastructure as Code", "Observability",
                 "DevSecOps", "Reliability Engineering"),
        groups=(),
        workflow_category="DevOps Workflows",
        sources="the project's own official documentation (for example kubernetes.io, docs.docker.com, developer.hashicorp.com, "
                "docs.github.com, jenkins.io, prometheus.io, grafana.com, helm.sh, argo-cd.readthedocs.io, sre.google)",
    ),
    "genai": Domain(
        key="genai",
        label="Generative AI",
        description="Building and operating LLM-powered applications, as taught in an AI-assisted DevOps course. "
                    "IN SCOPE: retrieval-augmented generation (chunking strategies, embedding models, vector databases and "
                    "approximate nearest-neighbour indexes, hybrid search, re-ranking, query rewriting, RAG evaluation such as "
                    "faithfulness and recall); prompting (system prompts, structured output, prompt injection and jailbreaks); "
                    "agents and tool use (function calling, ReAct, planning, multi-agent patterns, agent memory); LLM safety and "
                    "guardrails (PII redaction, moderation, output validation); evaluation and observability (LLM-as-judge, "
                    "tracing, evaluation datasets); LLMOps (caching, batching, model serving, cost control, model routing); "
                    "adapting LLMs (LoRA and other parameter-efficient fine-tuning, distillation, RLHF and DPO); and LLM "
                    "frameworks and tooling. "
                    "OUT OF SCOPE: classical machine learning (clustering, regression, statistics, probabilistic models), "
                    "generic deep-learning theory, computer vision, and research-only architectures.",
        concept_folder="genai_fundamentals",
        categories=("Generic Fundamentals", "LLM Fundamentals", "RAG & Retrieval", "Prompting Techniques", "Agents & Tools",
                    "Evaluation & Observability", "Model Adaptation", "Safety & Control", "Optimization"),
        id_prefix="",
        modules=("Fundamentals", "Retrieval", "Prompt Engineering", "Agents", "Evaluation", "Model Adaptation", "Safety", "Optimization"),
        groups=(),
        workflow_category="GenAI Workflows",
        sources="official documentation or the original paper (for example platform.openai.com/docs, docs.anthropic.com, "
                "docs.langchain.com, python.langchain.com, huggingface.co/docs, docs.trychroma.com, arxiv.org)",
    ),
}
