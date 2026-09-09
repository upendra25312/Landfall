"""
Generate the discovery-questionnaire catalog the web app serves, exports and
re-imports (PRD E11.25).

`docs/discovery-questionnaire.html` is the human source of truth. The web
container only ships `src/web/`, so this script projects the questionnaire into
that folder:

  src/web/discovery_catalog.json   — [{id, section, section_id, text, priority, feeds}]
  src/web/questionnaire.html       — a byte copy of the doc, so GET /questionnaire serves it

`feeds` (which estimate input a question drives) is maintained here — only a dozen
questions feed the model; the rest are context.

Run it after editing the questionnaire; `tests/test_discovery.py` fails if the
committed files drift from the HTML.
"""
from __future__ import annotations

import html
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_HTML = ROOT / "docs" / "discovery-questionnaire.html"
OUT_JSON = ROOT / "src" / "web" / "discovery_catalog.json"
OUT_HTML = ROOT / "src" / "web" / "questionnaire.html"

# question id -> the estimate input it grounds (see design.py / assemble.py)
FEEDS = {
    "B4": "target_region",
    "C1": "licensing_program",
    "C4": "azure_hybrid_benefit",
    "C5": "reserved_instances",
    "SC1": "compliance_scope",
    "SC2": "data_residency",
    "SC3": "security_baseline",
    "R1": "rpo_rto",
    "R3": "target_resilience",
    "N2": "connectivity",
    "N4": "ip_preservation",
    "A6": "internet_facing",
    "M3": "cutover_windows",
    "M5": "hard_stop_date",
    "O3": "maintenance_windows",
}


def build_catalog(src: str) -> list[dict]:
    secs = re.findall(
        r'<section id="([^"]+)">\s*<h2><span class="g">(\d+)</span>([^<]+)</h2>(.*?)</section>',
        src, re.S)
    cat: list[dict] = []
    for sid, _num, title, body in secs:
        title = html.unescape(title).strip()
        for m in re.finditer(
                r'<td class="id">([A-Z0-9]+)</td><td>(.*?)</td><td><span class="prio (must|should|nice)">',
                body, re.S):
            qid, text, prio = m.group(1), m.group(2), m.group(3)
            text = html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
            cat.append({"id": qid, "section": title, "section_id": sid,
                        "text": text, "priority": prio.upper(),
                        "feeds": FEEDS.get(qid)})
    return cat


def render(cat: list[dict], src_html: str) -> tuple[str, str]:
    return json.dumps(cat, ensure_ascii=False, indent=1) + "\n", src_html


def main(check: bool = False) -> int:
    src = SRC_HTML.read_text(encoding="utf-8")
    cat = build_catalog(src)
    if len(cat) < 60:
        print(f"ERROR: only parsed {len(cat)} questions — the HTML format changed", file=sys.stderr)
        return 2
    js, htm = render(cat, src)
    if check:
        ok = (OUT_JSON.read_text(encoding="utf-8") == js
              and OUT_HTML.read_text(encoding="utf-8") == htm)
        print("in sync" if ok else "DRIFT — run scripts/gen_discovery_catalog.py")
        return 0 if ok else 1
    OUT_JSON.write_text(js, encoding="utf-8")
    OUT_HTML.write_text(htm, encoding="utf-8")
    print(f"wrote {len(cat)} questions -> {OUT_JSON.relative_to(ROOT)} + {OUT_HTML.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(check="--check" in sys.argv))
