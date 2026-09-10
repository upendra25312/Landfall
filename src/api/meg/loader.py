"""Loader and cache for normalized MEG reference artifacts (Epic E15.2)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Cache dictionary for reference data loaded in memory
_MEG_CACHE: dict[str, dict[str, Any]] = {}


def get_meg_dir() -> Path:
    """Return the absolute path to the pinned references/meg directory."""
    # src/api/meg -> src/api -> src -> repo_root / references / meg
    return Path(__file__).resolve().parents[3] / "references" / "meg"


def _load_json(filename: str) -> dict[str, Any]:
    if filename in _MEG_CACHE:
        return _MEG_CACHE[filename]

    meg_dir = get_meg_dir()
    target = meg_dir / filename
    if not target.exists():
        raise FileNotFoundError(f"MEG reference artifact '{filename}' not found at {target}")

    content = json.loads(target.read_text(encoding="utf-8"))
    _MEG_CACHE[filename] = content
    return content


def load_metadata() -> dict[str, Any]:
    """Load and validate pinned MEG metadata."""
    meta = _load_json("metadata.json")
    required = ["source_repository", "source_commit_sha", "license"]
    for r in required:
        if r not in meta:
            raise ValueError(f"metadata.json missing required key: {r}")
    return meta


def load_lifecycle() -> dict[str, Any]:
    """Load MEG lifecycle phases and stage mappings."""
    return _load_json("lifecycle.json")


def load_checklist() -> dict[str, Any]:
    """Load normalized 15-category readiness checklist."""
    return _load_json("checklist.json")


def load_roles() -> dict[str, Any]:
    """Load standard migration functional roles and RACI/DACI defaults."""
    return _load_json("roles.json")


def load_risks() -> dict[str, Any]:
    """Load risk classification taxonomy, rating matrix, and trigger rules."""
    return _load_json("risks.json")


def load_wave_guidance() -> dict[str, Any]:
    """Load migration wave planning heuristics."""
    return _load_json("wave_guidance.json")


def load_all_meg() -> dict[str, Any]:
    """Load all MEG reference artifacts into a single combined payload."""
    return {
        "metadata": load_metadata(),
        "lifecycle": load_lifecycle(),
        "checklist": load_checklist(),
        "roles": load_roles(),
        "risks": load_risks(),
        "wave_guidance": load_wave_guidance(),
    }


def clear_meg_cache() -> None:
    """Clear memory cache (used primarily for test isolation)."""
    _MEG_CACHE.clear()
