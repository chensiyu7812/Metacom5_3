"""Semantic Capability Layer: source-bound, separately invocable semantic tools.

Tool outputs are candidates for the shared working state, never verified facts,
memory writes or reward. Deterministic host facts (speaker identity, dates,
source legality) are supplied by the host, not inferred by these models.
"""
