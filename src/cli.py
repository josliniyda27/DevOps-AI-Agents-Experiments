"""
Ask the knowledge-base chatbot a question.

    python -m src.cli "What is Amazon S3?"     # one question
    python -m src.cli                          # interactive; empty line or Ctrl-D to quit
"""

import argparse
import logging

from src.generation.chain import build_rag_chain
from src.guardrails import GuardrailViolation


def ask(chain, question: str) -> str:
    try:
        return chain.invoke(question)
    except GuardrailViolation as blocked:
        return f"[blocked: {blocked.category}] {blocked.reason}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the knowledge-base chatbot.")
    parser.add_argument("question", nargs="?", help="omit for interactive mode")
    parser.add_argument("-v", "--verbose", action="store_true", help="show guardrail log messages")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.ERROR, format="%(levelname)s %(name)s: %(message)s")

    try:
        chain = build_rag_chain()
    except ValueError as error:          # e.g. missing OPENAI_API_KEY
        raise SystemExit(f"Configuration error: {error}")

    if args.question:
        print(ask(chain, args.question))
        return

    print("Ask about the knowledge base (empty line to quit).")
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            break
        print(ask(chain, question))


if __name__ == "__main__":
    main()
