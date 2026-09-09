"""
Deterministic target landing-zone diagram (PRD E11.22 / §4.10).

`design_landing_zone` output  ->  a draw.io (mxGraph) XML document: the hub VNet
and every spoke as a swimlane, the hub components and a per-spoke workload tier
as cells, and peering / ExpressRoute / VPN / DR edges. Pure and fully offline —
no MCP round-trips, no browser. The rules (swimlane nesting, the Azure colour
palette, orthogonal edges, no hand-routed waypoints) are the vendored
`docs/diagram-authoring/` ruleset applied in code, not agent reasoning.

The `.drawio` file renders as-is in draw.io desktop and in the dashboard's
embedded viewer. Server-side `.svg` / `.png` rendering is the `ca-drawio`
container follow-up; this module is its input and stands alone without it.
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
