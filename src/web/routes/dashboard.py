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
def landing_zone_data(request: Request, e: str | None = None, optional: bool = False):
    """The Azure Pricing Calculator POE summary (landing_zone.json) for an engagement."""
    if (g := web_access._guard_eid(request, e)):
        return g
    blob = web_storage._read_estimate_blob("landing_zone.json", e)
    if blob is None:
        if optional:
            return Response(status_code=204)
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


@router.get("/dashboard/download/resource-plan-xlsx")
def download_resource_plan_xlsx(request: Request, e: str | None = None, snapshot: str | None = None):
    """Streams the standalone 15-sheet resource_plan.xlsx workbook (E15C.9)."""
    if (g := web_access._guard_eid(request, e)):
        return g
    blob = web_storage._snapshot_blob("latest.json", e, snapshot)
    pkg = json.loads(blob) if blob else {}
    cs = next((s["body"] for s in pkg.get("sections", []) if s.get("key") == "current_state"), {})
    wv = next((s["body"] for s in pkg.get("sections", []) if s.get("key") == "waves"), {})
    lz = next((s["body"] for s in pkg.get("sections", []) if s.get("key") == "landing_zone"), {})

    from resource import (
        analyze_capacity_and_constraints,
        build_project_plan,
        build_sow_resource_section,
        calculate_commercial_cost,
        derive_resource_demand,
        generate_resource_workbook,
    )
    demand = derive_resource_demand(
        server_count=cs.get("servers", 250),
        app_count=cs.get("applications", 31),
        spokes=len(lz.get("spokes", [])) if lz.get("spokes") else 9,
        regulated=bool(lz.get("regulated_scopes")),
        schedule=wv.get("schedule"),
        wave_plan={"waves": wv.get("waves", [])} if wv.get("waves") else None,
        engagement_id=e or "_default_/_default_",
    )
    capacity = analyze_capacity_and_constraints(demand)
    commercial = calculate_commercial_cost(demand)
    sow = build_sow_resource_section(demand, commercial)
    plan = build_project_plan(demand, wv.get("schedule"))
    wb_bytes = generate_resource_workbook(demand, capacity, commercial, sow, plan)

    name = (e or "landfall").replace("/", "-") + "-resource-plan"
    return Response(
        wb_bytes,
        media_type=web_runtime._EXPORT_MIME["xlsx"],
        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'}
    )


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
                         fmt: str = "svg", download: int = 0, optional: bool = False):
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
        if optional:
            return Response(status_code=204)
        return JSONResponse({"error": "no landing-zone diagram built yet"}, status_code=404)
    if download:
        name = (e or "landfall").replace("/", "-") + "-landing-zone"
        return Response(blob, media_type=mime, headers={
            "Content-Disposition": f'attachment; filename="{name}.{ext}"'})
    return Response(blob, media_type=mime)


@router.get("/dashboard/readiness")
def dashboard_readiness(request: Request, e: str | None = None, snapshot: str | None = None):
    """Returns the 5-state MEG readiness evaluation with evidence and drill-down details (E15D.2)."""
    if (g := web_access._guard_eid(request, e)):
        return g
    blob = web_storage._snapshot_blob("latest.json", e, snapshot)
    pkg = json.loads(blob) if blob else {}
    from meg.readiness import evaluate_readiness
    readiness = evaluate_readiness(pkg)

    role_map = {
        "discovery": "Lead Cloud Infrastructure Architect",
        "landing_zone": "Lead Cloud Infrastructure Architect",
        "business_readiness": "FinOps Analyst / Program Manager",
        "applications": "Application Owner / SME",
        "change_management": "Change Manager",
        "cutover_readiness": "DevOps & Operations Lead",
        "resource": "Program Manager",
    }
    criteria = []
    for it in readiness.get("items", []):
        cat = it.get("category", "")
        criteria.append({
            "id": it.get("id"),
            "category": cat.replace("_", " ").title(),
            "title": it.get("title"),
            "state": it.get("status"),
            "evidence": it.get("evidence"),
            "missing_decision": it.get("missing_input"),
            "responsible_role": role_map.get(cat, "Lead Cloud Architect"),
            "recommended_action": it.get("recommendation"),
            "guidance": it.get("guidance"),
        })

    return JSONResponse({
        "framework": readiness.get("framework"),
        "version": readiness.get("version"),
        "notice": readiness.get("notice"),
        "summary": readiness.get("summary"),
        "items": readiness.get("items"),
        "criteria": criteria,
        "by_category": readiness.get("by_category"),
    })


@router.get("/dashboard/resource-plan")
def dashboard_resource_plan(request: Request, e: str | None = None, snapshot: str | None = None):
    """Returns deterministic resource demand, scenarios, and capacity analysis (E15C / E15D)."""
    if (g := web_access._guard_eid(request, e)):
        return g
    blob = web_storage._snapshot_blob("latest.json", e, snapshot)
    pkg = json.loads(blob) if blob else {}
    cs = next((s["body"] for s in pkg.get("sections", []) if s.get("key") == "current_state"), {})
    wv = next((s["body"] for s in pkg.get("sections", []) if s.get("key") == "waves"), {})
    lz = next((s["body"] for s in pkg.get("sections", []) if s.get("key") == "landing_zone"), {})

    server_count = cs.get("servers", 250)
    app_count = cs.get("applications", 31)
    spokes = len(lz.get("spokes", [])) if lz.get("spokes") else 9
    regulated = bool(lz.get("regulated_scopes"))
    schedule = wv.get("schedule")
    wave_plan = {"waves": wv.get("waves", [])} if wv.get("waves") else None

    from resource import (
        analyze_capacity_and_constraints,
        calculate_commercial_cost,
        derive_resource_demand,
        generate_resource_scenarios,
    )
    demand = derive_resource_demand(
        server_count=server_count,
        app_count=app_count,
        spokes=spokes,
        regulated=regulated,
        schedule=schedule,
        wave_plan=wave_plan,
        engagement_id=e or "_default_/_default_",
    )
    scenarios = generate_resource_scenarios(
        server_count=server_count,
        app_count=app_count,
        spokes=spokes,
        regulated=regulated,
        schedule=schedule,
        wave_plan=wave_plan,
        engagement_id=e or "_default_/_default_",
    )
    capacity = analyze_capacity_and_constraints(demand, capacity_input=None)
    commercial = calculate_commercial_cost(demand)
    return JSONResponse({
        "demand": demand,
        "scenarios": scenarios,
        "capacity": capacity,
        "commercial": commercial,
    })


@router.get("/dashboard/explain")
def dashboard_explain(q: str = "landing_zone_topology"):
    """Returns the structured 6-part justification for a queried architectural topic (E15D.4)."""
    from recommendations.explain import explain_recommendation
    return JSONResponse(explain_recommendation(q))


@router.get("/dashboard/provenance")
def dashboard_provenance():
    """Returns authoritative assessment provenance metadata (E15D.6)."""
    from deliverable.provenance import get_provenance_metadata
    return JSONResponse(get_provenance_metadata())
