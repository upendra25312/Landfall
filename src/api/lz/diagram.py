"""
Deterministic target landing-zone diagram (PRD E11.22 / §4.10).

`design_landing_zone` output  ->  a draw.io (mxGraph) XML document: the hub VNet
and every spoke as a swimlane, the hub components and a per-spoke workload tier
as cells, and peering / ExpressRoute / VPN / DR edges. Pure and fully offline —
no MCP round-trips, no browser. The rules (swimlane nesting, the Azure colour
palette, orthogonal edges, no hand-routed waypoints) are the vendored
`docs/diagram-authoring/` ruleset applied in code, not agent reasoning.

Two outputs, both deterministic and browser-free:
  * `build_drawio(design)` — a draw.io (mxGraph) XML document, editable in draw.io
    desktop.
  * `build_svg(design)` — a self-contained SVG the dashboard renders inline and
    `to_docx` / `to_pptx` can embed (no external viewer, no container).

`.png` rasterisation + the full offline Azure icon set stay the `ca-drawio`
container follow-up (C27b); this module stands alone without it.
"""
from __future__ import annotations

import xml.sax.saxutils as _sx

# Azure colour palette (draw.io "Azure" convention, matches the vendored azure.md)
_C_HUB = "#0078D4"
_C_SPOKE = "#5E9BD1"
_C_REGULATED = "#B4009E"
_C_SANDBOX = "#787878"
_C_COMPONENT = "#E6F2FB"
_C_EDGE_PEER = "#0078D4"
_C_EDGE_HYBRID = "#00897B"
_C_EDGE_DR = "#D83B01"

_GRID = 10
_COL_W = 240          # swimlane width
_COL_GAP = 60
_CELL_W, _CELL_H = 200, 30
_HEADER = 26


def _esc(v) -> str:
    return _sx.escape(str(v if v is not None else ""), {'"': "&quot;", "'": "&apos;"})


class _XML:
    def __init__(self):
        self.cells: list[str] = []
        self._n = 1

    def _id(self, hint: str) -> str:
        self._n += 1
        return f"{hint}-{self._n}"

    def group(self, value: str, x: int, y: int, w: int, h: int, colour: str) -> str:
        cid = self._id("g")
        style = (f"swimlane;whiteSpace=wrap;html=1;startSize={_HEADER};"
                 f"fillColor=#FFFFFF;strokeColor={colour};fontColor={colour};"
                 "fontStyle=1;fontSize=12;align=center;verticalAlign=top;")
        self.cells.append(
            f'<mxCell id="{cid}" value="{_esc(value)}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return cid

    def cell(self, value: str, parent: str, x: int, y: int,
             w: int = _CELL_W, h: int = _CELL_H, colour: str = _C_COMPONENT) -> str:
        cid = self._id("c")
        style = (f"rounded=1;whiteSpace=wrap;html=1;fillColor={colour};"
                 "strokeColor=#0078D4;fontSize=11;align=left;spacingLeft=6;")
        self.cells.append(
            f'<mxCell id="{cid}" value="{_esc(value)}" style="{style}" vertex="1" parent="{_esc(parent)}">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return cid

    def edge(self, source: str, target: str, value: str, colour: str, dashed: bool = False) -> str:
        eid = self._id("e")
        style = (f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;"
                 f"strokeColor={colour};fontColor={colour};fontSize=10;"
                 + ("dashed=1;" if dashed else ""))
        self.cells.append(
            f'<mxCell id="{eid}" value="{_esc(value)}" style="{style}" edge="1" parent="1" '
            f'source="{_esc(source)}" target="{_esc(target)}">'
            f'<mxGeometry relative="1" as="geometry"/></mxCell>')
        return eid

    def document(self, title: str) -> str:
        body = "".join(self.cells)
        return (
            f'<mxfile host="Landfall" type="device">'
            f'<diagram name="{_esc(title)}" id="landing-zone">'
            f'<mxGraphModel dx="1200" dy="800" grid="1" gridSize="{_GRID}" guides="1" '
            f'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" math="0" shadow="0">'
            f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>{body}</root>'
            f'</mxGraphModel></diagram></mxfile>')


def _hub_components(design: dict) -> list[str]:
    hub = design.get("hub") or {}
    comps = list(hub.get("components") or [])
    egress = hub.get("spoke_egress")
    if egress and "firewall" in str(egress).lower() and not any("firewall" in c.lower() for c in comps):
        comps.append("Azure Firewall (forced-tunnel egress)")
    return comps or ["Hub VNet", "Azure Bastion", "Private DNS"]


def _spoke_label(sp: dict) -> str:
    zone = sp.get("zone") or "corp"
    tag = {"online": "Online", "corp": "Corp", "regulated": "Regulated",
           "sandbox": "Sandbox"}.get(zone, zone.title())
    name = sp.get("name") or f"{zone}-spoke"
    addr = sp.get("address_space")
    return f"{tag} · {name}" + (f"\n{addr}" if addr else "")


def _spoke_colour(sp: dict) -> str:
    return {"regulated": _C_REGULATED, "sandbox": _C_SANDBOX,
            "online": _C_HUB}.get(sp.get("zone"), _C_SPOKE)


def build_drawio(design: dict) -> str:
    """design_landing_zone output -> a draw.io XML string."""
    design = design or {}
    region = design.get("region") or "primary region"
    dr_region = design.get("dr_region")
    x = _XML()

    title = f"Azure Landing Zone — {region}" + (f" (DR {dr_region})" if dr_region else "")

    # --- hub swimlane (left column) -------------------------------------
    comps = _hub_components(design)
    hub_h = _HEADER + 20 + len(comps) * (_CELL_H + 10)
    hub = x.group(f"Hub VNet — {region}\n{(design.get('ip_plan') or {}).get('hub', '')}",
                  20, 40, _COL_W, hub_h, _C_HUB)
    for i, c in enumerate(comps):
        x.cell(c, hub, 20, _HEADER + 10 + i * (_CELL_H + 10), _COL_W - 40)

    # identity + connectivity note cell
    ident = (design.get("identity") or {}).get("model") or ""
    conn = (design.get("connectivity") or {}).get("model") or ""

    # --- spoke swimlanes (subsequent columns) --------------------------
    spokes = [s for s in (design.get("spokes") or []) if s.get("zone") != "sandbox"]
    spokes += [s for s in (design.get("spokes") or []) if s.get("zone") == "sandbox"]
    col = 1
    hub_ids = {}
    for sp in spokes:
        gx = 20 + col * (_COL_W + _COL_GAP)
        sh = _HEADER + 20 + 2 * (_CELL_H + 10)
        g = x.group(_spoke_label(sp), gx, 40, _COL_W, sh, _spoke_colour(sp))
        apps = sp.get("apps") or []
        x.cell(f"{len(apps)} application(s)" if apps else "workload subnet",
               g, 20, _HEADER + 10, _COL_W - 40)
        x.cell(f"env: {sp.get('env') or 'n/a'}", g, 20, _HEADER + 10 + _CELL_H + 10, _COL_W - 40)
        hub_ids[sp["name"]] = g
        x.edge(hub, g, "peering", _C_EDGE_PEER)
        col += 1

    # --- hybrid connectivity edge (on-prem) ---------------------------
    onprem = x.cell(f"On-premises\n{conn or 'ExpressRoute + VPN'}", "1",
                    20, 40 + hub_h + 40, _COL_W, 50, colour="#F2F2F2")
    x.edge(onprem, hub, conn or "ExpressRoute / VPN", _C_EDGE_HYBRID)

    if ident:
        x.cell(f"Identity: {ident}", "1", 20 + _COL_W + 20, 40 + hub_h + 45, _COL_W, 30, colour="#FFF4CE")

    # --- DR region ----------------------------------------------------
    if dr_region:
        drg = x.group(f"DR region — {dr_region}", 20, 40 + hub_h + 130, _COL_W * 2, 70, _C_EDGE_DR)
        drcell = x.cell("Paired region · ASR + native DB replication (tier 1–2) · GRS backup",
                        drg, 20, _HEADER + 8, _COL_W * 2 - 40, 30, colour="#FDE7E9")
        x.edge(hub, drg, "region pair", _C_EDGE_DR, dashed=True)

    # --- title banner ----------------------------------------------
    x.cell(title, "1", 20, 0, _COL_W * 3, 28, colour="#FFFFFF")

    return x.document(title)


# --------------------------------------------------------------- native SVG

def _svg_text(x: int, y: int, s: str, *, size: int = 11, weight: str = "normal",
              fill: str = "#1A1A1A", anchor: str = "start") -> str:
    return (f'<text x="{x}" y="{y}" font-family="Segoe UI,Helvetica,Arial,sans-serif" '
            f'font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}">{_esc(s)}</text>')


def _svg_box(x: int, y: int, w: int, h: int, *, fill: str, stroke: str,
             rx: int = 4, sw: int = 1, dash: str = "") -> str:
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')


def build_svg(design: dict) -> str:
    """design_landing_zone output -> a self-contained SVG string (no external refs)."""
    design = design or {}
    region = design.get("region") or "primary region"
    dr_region = design.get("dr_region")
    comps = _hub_components(design)
    spokes = [s for s in (design.get("spokes") or []) if s.get("zone") != "sandbox"] \
        + [s for s in (design.get("spokes") or []) if s.get("zone") == "sandbox"]

    pad, col_w, gap, row_h, head = 24, 230, 40, 30, 30
    top = 64
    hub_h = head + 12 + max(1, len(comps)) * (row_h + 8)
    spoke_h = head + 12 + 2 * (row_h + 8)
    cols = 1 + len(spokes)
    width = pad * 2 + cols * col_w + (cols - 1) * gap
    body_bottom = top + max(hub_h, spoke_h) + 110 + (90 if dr_region else 0)
    height = body_bottom + pad

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" font-family="Segoe UI,Helvetica,Arial,sans-serif">',
        f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>',
        _svg_text(pad, 28, f"Azure Landing Zone — {region}"
                  + (f"  ·  DR {dr_region}" if dr_region else ""), size=15, weight="bold",
                  fill=_C_HUB),
        _svg_text(pad, 46, f"{len(spokes)} spoke(s) · "
                  f"identity {(design.get('identity') or {}).get('model') or 'n/a'} · "
                  f"connectivity {(design.get('connectivity') or {}).get('model') or 'n/a'}",
                  size=10, fill="#5A6B76"),
    ]

    def _column(cx: int, label: str, sub: str, rows: list[str], colour: str, h: int) -> None:
        parts.append(_svg_box(cx, top, col_w, h, fill="#FFFFFF", stroke=colour, sw=2))
        parts.append(_svg_box(cx, top, col_w, head, fill=colour, stroke=colour))
        parts.append(_svg_text(cx + 10, top + 19, label, size=11, weight="bold", fill="#FFFFFF"))
        if sub:
            parts.append(_svg_text(cx + col_w - 10, top + 19, sub, size=9, fill="#EAF3FB", anchor="end"))
        for i, r in enumerate(rows):
            ry = top + head + 10 + i * (row_h + 8)
            parts.append(_svg_box(cx + 10, ry, col_w - 20, row_h, fill=_C_COMPONENT, stroke=_C_HUB))
            parts.append(_svg_text(cx + 18, ry + 19, r, size=10))

    # hub column
    hub_cx = pad
    _column(hub_cx, f"Hub VNet — {region}", (design.get("ip_plan") or {}).get("hub", ""),
            comps, _C_HUB, hub_h)

    # spoke columns + peering edges
    for j, sp in enumerate(spokes):
        cx = pad + (j + 1) * (col_w + gap)
        colour = _spoke_colour(sp)
        apps = sp.get("apps") or []
        _column(cx, (_spoke_label(sp).split("\n")[0]),
                sp.get("address_space") or "",
                [f"{len(apps)} application(s)" if apps else "workload subnet",
                 f"env: {sp.get('env') or 'n/a'}"], colour, spoke_h)
        y_mid = top + min(hub_h, spoke_h) / 2
        parts.append(f'<line x1="{hub_cx + col_w}" y1="{y_mid}" x2="{cx}" y2="{y_mid}" '
                     f'stroke="{_C_EDGE_PEER}" stroke-width="1.5"/>')

    # on-prem + hybrid edge
    op_y = top + max(hub_h, spoke_h) + 40
    parts.append(_svg_box(pad, op_y, col_w, 46, fill="#F2F2F2", stroke="#9AA7B0"))
    parts.append(_svg_text(pad + 10, op_y + 20, "On-premises", size=11, weight="bold"))
    parts.append(_svg_text(pad + 10, op_y + 36,
                           (design.get("connectivity") or {}).get("model") or "ExpressRoute + VPN",
                           size=9, fill="#5A6B76"))
    parts.append(f'<line x1="{pad + col_w // 2}" y1="{op_y}" x2="{pad + col_w // 2}" y2="{top + hub_h}" '
                 f'stroke="{_C_EDGE_HYBRID}" stroke-width="1.5"/>')
    parts.append(_svg_text(pad + col_w // 2 + 6, op_y - 6, "ExpressRoute / VPN", size=9,
                           fill=_C_EDGE_HYBRID))

    # DR region
    if dr_region:
        dr_y = op_y + 70
        parts.append(_svg_box(pad, dr_y, col_w * 2 + gap, 60, fill="#FDE7E9", stroke=_C_EDGE_DR,
                              dash="6 3"))
        parts.append(_svg_text(pad + 10, dr_y + 22, f"DR region — {dr_region}", size=11,
                               weight="bold", fill=_C_EDGE_DR))
        parts.append(_svg_text(pad + 10, dr_y + 40,
                               "Paired region · ASR + native DB replication (tier 1–2) · GRS backup",
                               size=9, fill="#7A2E33"))

    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------- MCP-call plan
# For when the `ca-drawio` engine is deployed: the same mapping as an ordered list
# of tool calls (create-group / add-cell-of-shape / add-edge / export-xml). Kept
# here so diagram.py stays the single source of the mapping.

def mcp_plan(design: dict) -> list[dict]:
    design = design or {}
    plan: list[dict] = []
    region = design.get("region") or "primary"
    plan.append({"tool": "create-group", "args": {"label": f"Hub VNet — {region}", "kind": "vnet"}})
    for c in _hub_components(design):
        plan.append({"tool": "add-cell-of-shape", "args": {"group": "hub", "label": c,
                                                           "shape": _shape_for(c)}})
    for sp in design.get("spokes") or []:
        plan.append({"tool": "create-group", "args": {"label": _spoke_label(sp).replace("\n", " "),
                                                      "kind": "vnet", "zone": sp.get("zone")}})
        plan.append({"tool": "add-edge", "args": {"source": "hub", "target": sp.get("name"),
                                                  "label": "peering", "color": _C_EDGE_PEER}})
    if design.get("dr_region"):
        plan.append({"tool": "add-edge", "args": {"source": "hub", "target": "dr",
                                                  "label": "region pair", "color": _C_EDGE_DR}})
    plan.append({"tool": "export-xml", "args": {}})
    return plan


_SHAPE = {
    "firewall": "mxgraph.azure.firewall",
    "bastion": "mxgraph.azure.azure_bastion",
    "gateway": "mxgraph.azure.vpn_gateway",
    "expressroute": "mxgraph.azure.express_route_circuits",
    "dns": "mxgraph.azure.dns",
    "domain controller": "mxgraph.azure.vm",
    "key vault": "mxgraph.azure.key_vault",
    "log analytics": "mxgraph.azure.log_analytics_workspaces",
}


def _shape_for(component: str) -> str:
    c = component.lower()
    for k, v in _SHAPE.items():
        if k in c:
            return v
    return "mxgraph.azure.virtual_network"


def diagram_meta(design: dict) -> dict:
    """The sidecar JSON stored next to landing_zone.drawio."""
    spokes = design.get("spokes") or []
    return {
        "region": design.get("region"),
        "dr_region": design.get("dr_region"),
        "hub_components": _hub_components(design),
        "spoke_count": len(spokes),
        "regulated": bool(design.get("regulated")),
        "identity": (design.get("identity") or {}).get("model"),
        "connectivity": (design.get("connectivity") or {}).get("model"),
        "renderer": "drawio-xml (client-side viewer); server-side svg/png pending ca-drawio",
        "source": "src/api/lz/diagram.py",
    }
