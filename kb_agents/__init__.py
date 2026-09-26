"""
Agentic workflow that grows the knowledge base. It runs separately from the chatbot:

    python -m kb_agents run --domain aws          # plan -> research -> write -> review -> validate -> stage
    python -m kb_agents merge --all               # merge staged entries, sync indexes, load into Chroma

Nothing reaches the knowledge base until it is merged.
"""
