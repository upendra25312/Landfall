"""E13.13 / §21 DoD — ca-calc as an event-driven Container Apps Job.

Structural checks on the Bicep (the real proof is an operator provision with
USE_CALC_JOB=true) + unit tests on the one-shot worker entrypoint.
"""
import asyncio
import os
import shutil
import subprocess
import sys

import pytest
from conftest import ROOT

_CALC = os.path.join(ROOT, "src", "calc")
if _CALC not in sys.path:
    sys.path.append(_CALC)


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------- bicep wiring

def test_use_calc_job_param_is_threaded_and_dormant():
    main = _read("infra", "main.bicep")
    assert "param useCalcJob bool = false" in main
    assert "useCalcJob: useCalcJob" in main
    params = _read("infra", "main.parameters.json")
    assert '"useCalcJob": { "value": "${USE_CALC_JOB=false}" }' in params

    res = _read("infra", "resources.bicep")
    assert "param useCalcJob bool = false" in res
    # the always-on Container App is now conditional on NOT using the job
    assert "resource calcApp 'Microsoft.App/containerApps@2024-10-02-preview' = if (!useCalcJob)" in res
    # the job is conditional on using it
    assert "resource calcJob 'Microsoft.App/jobs@2024-10-02-preview' = if (useCalcJob)" in res


def test_calc_job_is_event_driven_scale_to_zero():
    res = _read("infra", "resources.bicep")
    job = res[res.index("resource calcJob"):res.index("// ca-drawio", res.index("resource calcJob"))]
    assert "triggerType: 'Event'" in job
    assert "minExecutions: 0" in job
    assert "type: 'azure-queue'" in job
    assert "queueName: calcJobsQueue.name" in job
    assert "identity: uami.id" in job           # managed-identity auth on the KEDA scaler
    assert "command: [ 'python', 'job.py' ]" in job
    assert "'azd-service-name': 'calc'" in job  # azd deploy calc targets it


def test_default_still_deploys_the_always_on_app():
    assert "USE_CALC_JOB=false" in _read("infra", "main.parameters.json")
    assert "param useCalcJob bool = false" in _read("infra", "resources.bicep")


@pytest.mark.skipif(not (shutil.which("az") or shutil.which("az.cmd")), reason="az not installed")
def test_bicep_compiles(tmp_path):
    az = shutil.which("az") or shutil.which("az.cmd")
    r = subprocess.run([az, "bicep", "build", "--file", os.path.join(ROOT, "infra", "main.bicep"),
                        "--outfile", str(tmp_path / "main.json")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# --------------------------------------------------------------- worker.run_once

class _Msg:
    def __init__(self, content):
        self.content = content
        self.dequeue_count = 1


class _FakeQueue:
    def __init__(self, batches):
        self.batches = list(batches)      # list of lists of _Msg
        self.deleted = []
        self.queue_name = "calc-jobs"

    def receive_messages(self, visibility_timeout=None, max_messages=1):
        return iter(self.batches.pop(0) if self.batches else [])

    def delete_message(self, m):
        self.deleted.append(m)


def _worker():
    import importlib
    import worker
    importlib.reload(worker)
    return worker


def test_run_once_drains_then_exits(monkeypatch):
    worker = _worker()
    q = _FakeQueue([[_Msg('{"engagement":"a/b"}'), _Msg('{"engagement":"c/d"}')], []])
    processed = []

    async def _fake_process(blob, job):
        processed.append(job["engagement"])

    monkeypatch.setattr(worker, "_clients", lambda: (object(), q))
    monkeypatch.setattr(worker, "_process", _fake_process)

    n = asyncio.run(asyncio.wait_for(worker.run_once(), timeout=5))
    assert n == 2
    assert processed == ["a/b", "c/d"]
    assert len(q.deleted) == 2           # both messages removed


def test_run_once_returns_zero_on_empty_queue(monkeypatch):
    worker = _worker()
    monkeypatch.setattr(worker, "_clients", lambda: (object(), _FakeQueue([[]])))
    monkeypatch.setattr(worker, "_process", lambda b, j: None)
    assert asyncio.run(worker.run_once()) == 0


def test_run_once_deletes_a_poison_message_without_processing(monkeypatch):
    worker = _worker()
    m = _Msg('{"engagement":"x/y"}')
    m.dequeue_count = 99
    q = _FakeQueue([[m], []])
    calls = []
    monkeypatch.setattr(worker, "_clients", lambda: (object(), q))
    monkeypatch.setattr(worker, "_process", lambda b, j: calls.append(1))
    n = asyncio.run(worker.run_once())
    assert n == 0 and calls == [] and len(q.deleted) == 1


# --------------------------------------------------------------- job.py entrypoint

def test_job_main_fails_without_queue_url(monkeypatch):
    monkeypatch.delenv("STORAGE_QUEUE_URL", raising=False)
    import importlib
    import job
    importlib.reload(job)
    assert job.main() == 1


def test_job_main_exits_zero_on_success(monkeypatch):
    monkeypatch.setenv("STORAGE_QUEUE_URL", "https://x.queue.core.windows.net")
    import importlib
    import worker
    import job
    importlib.reload(worker)
    importlib.reload(job)

    async def _ok():
        return 3
    monkeypatch.setattr(worker, "run_once", lambda *a, **k: _ok())
    assert job.main() == 0
