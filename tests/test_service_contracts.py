"""C53 Function registration, tool contracts, and the legacy durable batch path."""
import asyncio
import io
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from conftest import ROOT


@pytest.fixture(scope="module")
def functions():
    import function_app
    return function_app, function_app.app.get_functions()


def test_every_openapi_tool_maps_to_a_registered_function(functions):
    _, registered = functions
    routes = set()
    for function in registered:
        trigger = function.get_trigger().get_dict_repr()
        if trigger["type"] == "httpTrigger":
            routes.update(("/" + trigger["route"], str(method).lower()) for method in trigger["methods"])
    specs = list((Path(ROOT) / "src/api/openapi").glob("*.json"))
    assert len(specs) == 18
    for path in specs:
        for url, operations in json.loads(path.read_text(encoding="utf-8"))["paths"].items():
            for method in operations.keys() & {"get", "post", "put", "delete"}:
                assert (url, method) in routes, (path.name, url, method)


def test_durable_and_ingestion_triggers_are_registered(functions):
    _, registered = functions
    names = {function.get_function_name() for function in registered}
    assert {"start", "orchestrator", "parse_sheet", "ask", "write_results", "ingest_blob"} <= names
    assert len(names) == len(registered)


@pytest.fixture
def batch(functions, monkeypatch):
    module, _ = functions
    store = {}

    class Blob:
        def __init__(self, key):
            self.key = key

        def download_blob(self):
            return SimpleNamespace(readall=lambda: store[self.key])

        def upload_blob(self, data, **_kwargs):
            store[self.key] = data.read() if hasattr(data, "read") else data

    monkeypatch.setattr(module, "_blob_client", lambda: SimpleNamespace(
        get_blob_client=lambda container, name: Blob((container, name))))
    return module, store


def workbook(columns):
    out = io.BytesIO()
    pd.DataFrame(columns).to_excel(out, index=False)
    return out.getvalue()


def test_batch_starter_copies_workbook_and_starts_orchestration(batch):
    module, store = batch
    seen = []

    async def start_new(name, **kwargs):
        seen.append((name, kwargs))
        return "offline-instance"

    starter = inspect.unwrap(module.start.build().get_user_function())
    asyncio.run(starter(SimpleNamespace(name="questions/client.xlsx", read=lambda: b"sheet"),
                             SimpleNamespace(start_new=start_new)))
    assert store["work", "client.xlsx"] == b"sheet"
    assert seen == [("orchestrator", {"client_input": "client.xlsx"})]


def test_batch_parse_and_output_preserve_questions_and_status(batch):
    module, store = batch
    store["work", "client.xlsx"] = workbook({"Question": ["What is the cost?", "What is the plan?"]})
    assert module.parse_sheet("client.xlsx") == ["What is the cost?", "What is the plan?"]
    module.write_results({"name": "client.xlsx", "rows": [
        {"q": "What is the cost?", "answer": "Needs discovery", "cites": "input", "status": "ok"}]})
    result = pd.read_excel(io.BytesIO(store["answers", "client_answered.xlsx"]))
    assert result.to_dict("records") == [{"Question": "What is the cost?", "Answer": "Needs discovery",
                                          "Sources": "input", "Status": "ok"}]


@pytest.mark.parametrize("columns,expected", [({"Other": ["x"]}, "error"),
                                             ({"Question": ["x"] * 301}, "TOO_MANY_ROWS")])
def test_batch_rejects_missing_column_and_oversized_workbook(batch, columns, expected):
    module, store = batch
    store["work", "client.xlsx"] = workbook(columns)
    if expected == "error":
        with pytest.raises(ValueError):
            module.parse_sheet("client.xlsx")
    else:
        assert module.parse_sheet("client.xlsx") == expected


def test_batch_agent_failure_is_explicit_and_empty_question_does_not_call_model(batch, monkeypatch):
    module, _ = batch
    calls = []

    def unavailable():
        calls.append(1)
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(module, "_openai_client", unavailable)
    assert module.ask(" ")["status"] == "empty" and not calls
    result = module.ask("What is the cost?")
    assert result["answer"] == "" and result["status"].startswith("error:")
