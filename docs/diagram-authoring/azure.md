# draw.io Azure diagram rules (vendored authoring reference)

**Source:** `drawio-mcp-diagramming` skill — `azure.md`
(<https://github.com/thomast1906/github-copilot-agent-skills/tree/main/.github/skills/drawio-mcp-diagramming>),
distilled **2026-09-09**. Applied in code by `src/api/lz/diagram.py` — not agent reasoning.

## Palette

| Element | Colour | Use |
|---|---|---|
| Hub VNet container | `#0078D4` (Azure blue) | the connectivity hub swimlane border + title |
| Landing-zone spoke container | `#5E9BD1` | Corp / Online workload spokes |
| Regulated spoke container | `#B4009E` | a spoke carrying a compliance scope (PCI, HIPAA, …) |
| Sandbox container | `#787878` | non-production experimentation |
| Component cell fill | `#E6F2FB` | Firewall, Bastion, Gateway, DNS, Key Vault, Log Analytics, DCs |
| Peering edge | `#0078D4` | hub ↔ spoke VNet peering |
| Hybrid edge | `#00897B` | ExpressRoute / VPN to on-premises |
| DR edge | `#D83B01`, dashed | primary ↔ paired region |

## Structure

- One **swimlane group per VNet** (`startSize=24`, title in the header). Spokes are
  siblings of the hub, laid out left-to-right; the hub is column 0.
- Components live **inside** their VNet's swimlane as child cells (`parent=<group id>`).
- Cross-container edges attach to the **group**, not a child cell, and use
  `parent="1"` (the layer), never a hand-routed waypoint.
- Edges are `edgeStyle=orthogonalEdgeStyle` — the layout pass routes them; do not
  write `<mxPoint>` waypoints.
- Label the diagram with the engagement's real `target_region` / `dr_region` and the
  hub components from the actual design — never a generic template.

## Icons

The `ca-drawio` engine (`simonkurtz-MSFT/drawio-mcp-server`) ships 700+ offline Azure
icons; `diagram.py::_shape_for` maps a component name → an `mxgraph.azure.*` shape key
for that path. The standalone `.drawio` this module emits uses styled rounded cells
(always render in any viewer); open it in draw.io desktop to swap in the full icons.
