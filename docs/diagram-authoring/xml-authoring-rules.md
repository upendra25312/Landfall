# draw.io XML authoring rules (vendored authoring reference)

**Source:** `drawio-mcp-diagramming` skill — `xml-authoring-rules.md`, distilled **2026-09-09**.
Applied by `src/api/lz/diagram.py`.

- The document is `<mxfile><diagram><mxGraphModel><root>…</root></mxGraphModel></diagram></mxfile>`.
- `<root>` always starts with `<mxCell id="0"/>` and `<mxCell id="1" parent="0"/>` — the
  base layer. Every real cell has `parent="1"` or the id of a container.
- A shape cell: `vertex="1"`, a `<mxGeometry x y width height as="geometry"/>`, and a
  `style` string of `key=value;` pairs.
- An edge cell: `edge="1"`, `source=`/`target=` cell ids, `<mxGeometry relative="1" as="geometry"/>`.
- A container / swimlane: `style="swimlane;startSize=24;…"`; children set `parent` to it
  and their geometry is **relative to the container's top-left**.
- **Escape** `& < > " '` in every `value` and `style` (`xml.sax.saxutils.escape`).
- IDs are stable strings; never reuse an id. `diagram.py` uses `<hint>-<counter>`.
- No waypoints: let `edgeStyle=orthogonalEdgeStyle` + the layout pass route edges.
- Keep it one page (`page="1"`), grid on (`gridSize=10`).
