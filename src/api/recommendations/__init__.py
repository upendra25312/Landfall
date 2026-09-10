"""
Recommendations and Explanations Package (PRD E15D.4, E15D.5).
"""
from __future__ import annotations

from recommendations.explain import (
    compare_baseline_to_live_guidance,
    explain_recommendation,
    RecommendationExplanation,
)

__all__ = [
    "RecommendationExplanation",
    "compare_baseline_to_live_guidance",
    "explain_recommendation",
]
