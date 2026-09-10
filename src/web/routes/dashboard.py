"""Landfall dashboard helpers and HTTP routes.

Extracted in C52; HTTP contracts and behavior are preserved.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
import json
import web_access
import web_runtime
import web_storage

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """The assessment dashboard — an Azure Migrate–style read of the published estimate."""
    return (web_runtime._HERE / "dashboard.html").read_text(encoding="utf-8")


@router.get("/dashboard/data")
def dashboard_data(request: Request, e: str | None = None, snapshot: str | None = None):
    if (g := web_access._guard_eid(request, e)):
        return g
    blob = web_storage._snapshot_blob("latest.json", e, snapshot)
    if blob is None:
        return JSONResponse({"error": "no estimate published"}, status_code=404)
    return JSONResponse(json.loads(blob))


@router.get("/dashboard/landing-zone")
def landing_zone_data(request: Request, e: str | None = None):
    """The Azure Pricing Calculator POE summary (landing_zone.json) for an engagement."""
    if (g := web_access._guard_eid(request, e)):
        return g
    blob = web_storage._read_estimate_blob("landing_zone.json", e)
    if blob is None:
        return JSONResponse({"error": "no Pricing Calculator estimate built yet"}, status_code=404)
    return JSONResponse(json.loads(blob))


@router.get("/dashboard/download/landing-zone-xlsx")
def landing_zone_xlsx(request: Request, e: str | None = None):
    """Stream the Azure Pricing Calculator's own Excel export — the POE artifact."""
    if (g := web_access._guard_eid(request, e)):
        return g
    blob = web_storage._read_estimate_blob("landing_zone.xlsx", e)
    if blob is None:
        return JSONResponse({"error": "no Pricing Calculator estimate built yet"}, status_code=404)
    name = (e or "landfall").replace("/", "-") + "-landing-zone-POE"
    return Response(blob, media_type=web_runtime._EXPORT_MIME["xlsx"], headers={
        "Content-Disposition": f'attachment; filename="{name}.xlsx"'})


@router.get("/dashboard/download/{fmt}")
def dashboard_download(fmt: str, request: Request, e: str | None = None,
                       snapshot: str | None = None):
    if (g := web_access._guard_eid(request, e)):
        return g
    fmt = fmt.lower().lstrip(".")
    if fmt not in web_runtime._EXPORT_MIME:
        return JSONResponse({"error": "format must be xlsx | docx | pptx"}, status_code=400)
    blob = web_storage._snapshot_blob(f"latest.{fmt}", e, snapshot)
    if blob is None:
        return JSONResponse({"error": f"no {fmt} export published"}, status_code=404)
    name = (e or "landfall-estimate").replace("/", "-")
    return Response(blob, media_type=web_runtime._EXPORT_MIME[fmt], headers={
        "Content-Disposition": f'attachment; filename="{name}.{fmt}"'})


@router.get("/dashboard/landing-zone-diagram")
def landing_zone_diagram(request: Request, e: str | None = None,
                         fmt: str = "svg", download: int = 0):
    """The engagement's target landing-zone diagram (E11.22). `fmt=svg` (default) is
    the self-contained SVG the dashboard renders inline; `fmt=drawio` is the editable
    source; `?download=1` sends it as a file."""
    if (g := web_access._guard_eid(request, e)):
        return g
    fmt = fmt.lower()
    if fmt == "drawio":
        blob = web_storage._read_estimate_blob("landing_zone.drawio", e)
        mime, ext = "application/xml", "drawio"
    elif fmt == "png":
        blob = web_storage._read_estimate_blob("landing_zone.png", e)
        mime, ext = "image/png", "png"
    else:
        blob = web_storage._read_estimate_blob("landing_zone.svg", e) or web_storage._read_estimate_blob("landing_zone.drawio", e)
        mime, ext = ("image/svg+xml", "svg") if (blob and blob.lstrip().startswith(b"<svg")) \
            else ("application/xml", "drawio")
    if blob is None:
        return JSONResponse({"error": "no landing-zone diagram built yet"}, status_code=404)
    if download:
        name = (e or "landfall").replace("/", "-") + "-landing-zone"
        return Response(blob, media_type=mime, headers={
            "Content-Disposition": f'attachment; filename="{name}.{ext}"'})
    return Response(blob, media_type=mime)
