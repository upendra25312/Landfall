"""Landfall web storage helpers.

Extracted in C52; HTTP contracts and behavior are preserved.
"""

import json
import web_runtime

_ESTIMATE = {"prefix": "estimate", "container": "answers"}


_blob_state: dict = {}


def _estimate_container():
    if "cc" not in _blob_state:
        from azure.storage.blob import BlobServiceClient

        if not web_runtime.STORAGE_URL:
            raise RuntimeError("STORAGE_URL not set")
        svc = BlobServiceClient(web_runtime.STORAGE_URL, credential=web_runtime._cred)
        _blob_state["cc"] = svc.get_container_client(_ESTIMATE["container"])
    return _blob_state["cc"]


def _estimate_prefixes(engagement: str | None) -> list[str]:
    """A named engagement reads only its own artifacts; legacy fallback is unscoped."""
    eid = (engagement or "").strip().strip("/")
    if eid:
        parts = eid.split("/")
        import re
        if len(parts) != 2 or not all(re.fullmatch(r"[a-z0-9_][a-z0-9_-]{0,49}", p) for p in parts):
            return []
        return [f"engagements/{eid}/estimate"]
    return ["engagements/_default_/_default_/estimate", "estimate"]


def _read_estimate_blob(name: str, engagement: str | None = None) -> bytes | None:
    for prefix in _estimate_prefixes(engagement):
        try:
            data = _estimate_container().download_blob(f"{prefix}/{name}").readall()
        except Exception:  # noqa: BLE001 - missing blob -> try the next location
            continue
        if prefix == "estimate":  # pre-E11 flat path — one-release back-compat shim
            web_runtime.log.warning("serving %s from the legacy flat estimate/ path — run "
                            "scripts/migrate_to_default_engagement.py --apply", name)
        return data
    return None


def _raw_container():
    if "raw" not in _blob_state:
        from azure.storage.blob import BlobServiceClient
        if not web_runtime.STORAGE_URL:
            raise RuntimeError("STORAGE_URL not set")
        svc = BlobServiceClient(web_runtime.STORAGE_URL, credential=web_runtime._cred)
        _blob_state["raw"] = svc.get_container_client("raw")
    return _blob_state["raw"]


def _calc_regions() -> list[str]:
    if "regions" not in _blob_state:
        try:
            _blob_state["regions"] = json.loads(
                (web_runtime._HERE / "calc_regions.json").read_text(encoding="utf-8")).get("regions", [])
        except Exception:  # noqa: BLE001
            _blob_state["regions"] = ["swedencentral", "westeurope", "northeurope",
                                      "eastus", "eastus2", "westus2", "uksouth"]
    return _blob_state["regions"]


def _list_files(base: str) -> list[dict]:
    cc = _raw_container()
    out = []
    for sub in ("inventory", "docs"):
        for b in cc.list_blobs(name_starts_with=f"{base}/{sub}/", include=["metadata"]):
            fn = b.name.rsplit("/", 1)[-1]
            if not fn or fn == ".keep":
                continue
            md = getattr(b, "metadata", None) or {}
            out.append({
                "name": fn, "kind": sub, "size": b.size,
                "uploaded_at": (b.last_modified.isoformat() if b.last_modified else None),
                "uploaded_by": md.get("uploaded_by"),
                "profile": md.get("profile") or "",
                "rows": int(md.get("rows") or 0), "columns": int(md.get("columns") or 0),
            })
    out.sort(key=lambda x: x.get("uploaded_at") or "", reverse=True)
    return out


def _snapshot_blob(name: str, engagement: str | None, snapshot: str | None) -> bytes | None:
    """Read `name` from a history/<snapshot>/ folder, or the live latest.* if no
    snapshot is given (E11.8)."""
    if not snapshot:
        return _read_estimate_blob(name, engagement)
    eid = (engagement or "").strip().strip("/")
    stamp = "".join(ch for ch in snapshot if ch.isalnum() or ch == "Z")
    if not eid or not stamp:
        return None
    try:
        return _estimate_container().download_blob(
            f"engagements/{eid}/history/{stamp}/{name}").readall()
    except Exception:  # noqa: BLE001
        return None
