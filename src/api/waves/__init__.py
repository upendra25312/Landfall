"""
Wave / move-group engine (PRD E4).

  from waves.disposition import score_dispositions
  from waves.plan import plan_waves

`score_dispositions` — rule-derived 6R candidate + rationale per application (E4.2).
`plan_waves` — the server dependency graph rolled up to applications, clustered into
affinity move-groups, ordered into risk-first waves with entry/exit criteria and
blocking dependencies (E4.1).

Both deterministic and pure — the agent explains the output, it never invents it.
"""
from .disposition import score_dispositions, score_one
from .plan import plan_waves

__all__ = ["score_dispositions", "score_one", "plan_waves"]
