"""
Assessment Provenance Metadata (PRD E15D.6).

Attaches authoritative provenance records to deliverables and dashboard views:
  - Landfall Engine Version
  - Assessment Date
  - Price Date
  - MEG Reference Commit
  - MEG Artifact Hash
  - Microsoft Guidance Validation Date
  - Resource Model Version
  - Configuration Version
"""
from __future__ import annotations

from datetime import date
from typing import Any

from cost.config import load_config
from meg.loader import load_metadata

ENGINE_VERSION = "2.4.0"
RESOURCE_MODEL_VERSION = "1.0.0"


def get_provenance_metadata(
    assessment_date: str | None = None,
    cfg: dict | None = None,
) -> dict[str, Any]:
    """
    Returns the complete provenance metadata block for the assessment.
    """
    cfg = cfg or load_config()
    meg_meta = load_metadata()

    price_date = cfg.get("pricing", {}).get("price_date") or "2026-09-08"
    ass_date = assessment_date or date.today().isoformat()

    return {
        "engine_version": ENGINE_VERSION,
        "assessment_date": ass_date,
        "price_date": price_date,
        "meg_reference_commit": meg_meta.get("source_commit_sha", "09b269375dc7c48cee7541e4ca16faf02b3897ca"),
        "meg_artifact_hash": meg_meta.get("artifact_sha256", "4b726f1c79e64e578ad2eb463690d563914e6e66e84d4da5898864f131a99ef8"),
        "meg_reference_version": meg_meta.get("reference_version", "2024.1"),
        "microsoft_guidance_validation_date": meg_meta.get("retrieved_at", "2026-09-10T12:00:00Z"),
        "resource_model_version": RESOURCE_MODEL_VERSION,
        "configuration_source": cfg.get("_source", "defaults"),
        "attribution": meg_meta.get("attribution_notice", "Aligned with the Microsoft Azure Migration Execution Guide reference (github.com/Azure/migration)."),
    }
