"""
Generation and Context Engineering module.
Exposes the RAG chain and context formatting utilities.
"""
from src.generation.chain import build_rag_chain, build_rag_pipeline
from src.generation.context_builder import format_docs_to_xml
from src.generation.prompts import NO_ANSWER, SYSTEM_PROMPT, rag_prompt

__all__ = [
    "build_rag_chain",
    "build_rag_pipeline",
    "format_docs_to_xml",
    "rag_prompt",
    "NO_ANSWER",
    "SYSTEM_PROMPT",
]