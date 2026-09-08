"""
Structured estimate deliverable (PRD E5).

  from deliverable.assemble import assemble_estimate
  from deliverable.effort import estimate_effort

`assemble_estimate` stitches the outputs of the other tools (compute / storage /
run-rate cost, landing zone, dispositions, waves) plus an inventory summary into
ONE package: 8 sections, a stable ID + calculation appendix on every headline
figure (E5.2), and a machine-built assumptions & exclusions register collected
across the whole run (E5.3). `estimate_effort` is the parametric person-day model
the package uses (E6.2, basic).

Deterministic and pure — no network, tool outputs are injected.
"""
from .effort import estimate_effort
from .assemble import assemble_estimate, render_markdown

__all__ = ["estimate_effort", "assemble_estimate", "render_markdown"]
