# tests/browser/ — Playwright browser-automation harness (PRD §4.17 / E13.15)

`TestClient` proves the JSON a route returns. This proves the **page actually
renders and works** — real JS execution, real `fetch`, the real strict
Content-Security-Policy, real layout. A CSP violation or a syntax error in a static
asset surfaces here as a console/page error.

> Its first run (C48) caught a fatal `\'` double-escape in `static/chat.js` that had
> broken the **entire chat page** since C41 — `<script src=chat.js>` never parsed,
> so no engagement picker, no welcome, no chat, no pipeline strip. Four `azd deploy
> web` runs and a dozen `TestClient` substring assertions never saw it.

## Run

C53 adds create → upload → analysis → chat/reload and empty-engagement →
questionnaire journeys in `test_system_journeys.py`. The fixture uses real CSV
normalization but in-memory storage and canned agent responses; it does not
claim a live Azure tool or model round-trip. CI runs this suite and uploads its
JUnit report/screenshots. See [the system plan](../SYSTEM-TEST-PLAN.md).

```bash
BROWSER=1 ./.venv2/Scripts/python.exe -m pytest tests/browser -q
```

Needs `pytest-playwright` (in `tests/requirements-dev.txt`) and a Chromium build:

```bash
./.venv2/Scripts/python.exe -m playwright install chromium
```

Skipped in the normal suite (`conftest.py` gates on `BROWSER=1`). A session fixture
boots `serve.py` — `src/web/app.py` with an **in-memory blob store** (seeded with a
demo engagement) and a **canned agent** — on a free port, and tears it down after.
Headless-Chromium-in-CI against an ephemeral `azd up` is **E13.16**.

You can also drive it by hand / with the Playwright MCP:

```bash
./.venv2/Scripts/python.exe tests/browser/serve.py --port 8850   # then open http://127.0.0.1:8850
```

## The core regression journeys

Every cycle that touches a user-visible surface runs the relevant spec **red → green**
and drops a before/after screenshot in the PDCA Check step (§4.17).

| # | Journey | Spec | Status |
|---|---|---|---|
| a | `/` loads under the strict CSP, 0 console/page errors, `chat.js` + `chat.css` load, the welcome + prompt cards render | `test_chat_page.py::test_chat_page_loads_clean` | ✅ |
| b | the engagement `<select>` is populated from `/api/engagements`; the choice persists across reload (user never types the id) | `test_chat_page.py::test_engagement_picker_is_populated` | ✅ |
| c | upload a sample inventory → the manifest row flips to ✓ with the detected profile + row count | — | ⬜ MCP-driven for now; automate with a seeded `UploadFile` |
| d | Start analysis → the DQ card + the pipeline strip advance | `test_chat_page.py::test_pipeline_strip_reflects_state` (strip state; the Start-analysis click path is ⬜) | 🟡 |
| e | a prompt card → the answer renders as Markdown; "Download as Excel" appears on a tabular answer | — | ⬜ |
| f | a pre-analysis chat → a one-time, non-blocking hint, not a block; the answer still arrives | `test_chat_page.py::test_pre_analysis_chat_gets_a_nonblocking_hint` | ✅ |

## Gotchas

C52 adds `test_router_journey.py`: a tabular chat answer survives reload and the
actual Excel button downloads a workbook containing the question and provenance.
Set `C52_SCREENSHOT_DIR` to retain desktop/mobile screenshots of this journey.
The offline agent now supplies a canned tabular tool result. Azure-client stubs
live on `web_runtime` and `web_storage`, the modules that own those dependencies.

- **`page.wait_for_function("<string>")` does not work here** — evaluating a string
  as JS violates `script-src 'self'` (no `unsafe-eval`). Use the auto-retrying
  `expect(locator)` assertions from `playwright.sync_api`.
- `<option>` elements inside a `<select>` are not "visible" to Playwright — wait
  with `.wait_for(state="attached")` or assert on the `<select>` value.
- `serve.py`'s in-memory store implements just enough of the blob container +
  blob-client surface for the pages under test; extend `_Store` / `_BlobClient`
  when a new journey needs more.
