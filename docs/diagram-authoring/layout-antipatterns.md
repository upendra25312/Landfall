# Landing-zone diagram — layout anti-patterns (vendored authoring reference)

**Source:** `drawio-mcp-diagramming` skill — layout guidance, distilled **2026-09-09**.

Avoid, in the generated `.drawio`:

- **Hand-routed edges** — no `<mxPoint>` waypoints. Pick a layout pass
  (`libavoid` / orthogonal) and let it route.
- **Free-floating components** — every Azure component belongs *inside* a VNet
  swimlane, not loose on the canvas.
- **A generic template** — the diagram must reflect *this* engagement: real region
  names, the actual hub components, the real spoke list (no PCI app → no PCI spoke).
- **Icon soup** — one cell per component, labelled; don't stack five icons in a box.
- **Cross-container edges to child cells** — attach hub↔spoke edges to the spoke's
  swimlane group, not to a subnet cell inside it.
- **Colour drift** — use the `azure.md` palette exactly; the hub is Azure blue,
  regulated spokes magenta, DR edges dashed orange.
- **Multi-page** — one page; the landing zone is one picture.
