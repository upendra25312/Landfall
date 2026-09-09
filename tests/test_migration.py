"""C23 / E11.11 — the pre-E11 -> _default_/_default_ migration: dry-run changes
nothing; --apply moves the flat blobs and writes the seed manifest. (SQL side is
covered by the script's own guardrails; not exercised offline.)
"""
import importlib
import json
import os
import sys

import pytest
from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "scripts"))


class _Down:
    def __init__(self, d):
        self._d = d

    def readall(self):
        return self._d


class _Container:
    def __init__(self, store):
        self.store = store

    def list_blobs(self, name_starts_with=""):
        for k in list(self.store):
            if k.startswith(name_starts_with):
                class _B:
                    pass
                b = _B()
                b.name = k
                yield b

    def download_blob(self, key):
        if key not in self.store:
            raise KeyError(key)
        return _Down(self.store[key])

    def upload_blob(self, key, data, overwrite=False):
        self.store[key] = data if isinstance(data, bytes) else bytes(data)

    def delete_blob(self, key):
        del self.store[key]


class _Svc:
    def __init__(self, raw, answers):
        self._c = {"raw": _Container(raw), "answers": _Container(answers)}

    def get_container_client(self, name):
        return self._c[name]


@pytest.fixture()
def mig(monkeypatch):
    m = importlib.import_module("migrate_to_default_engagement")
    raw = {"inventory/servers.csv": b"a,b\n1,2\n", "docs/network.md": b"# net"}
    answers = {"estimate/latest.json": b"{}", "estimate/latest.xlsx": b"xlsx"}
    svc = _Svc(raw, answers)
    monkeypatch.setattr(m, "_svc", lambda: svc)
    return m, svc, raw, answers


def test_dry_run_changes_nothing(mig, capsys):
    m, svc, raw, answers = mig
    m.main(["--skip-sql"])
    assert set(raw) == {"inventory/servers.csv", "docs/network.md"}
    assert set(answers) == {"estimate/latest.json", "estimate/latest.xlsx"}
    out = capsys.readouterr().out
    assert "DRY-RUN" in out and "4 blob(s) to move" in out


def test_apply_moves_blobs_and_writes_manifest(mig):
    m, svc, raw, answers = mig
    m.main(["--apply", "--skip-sql"])

    assert "inventory/servers.csv" not in raw
    assert raw["engagements/_default_/_default_/inventory/servers.csv"] == b"a,b\n1,2\n"
    assert raw["engagements/_default_/_default_/docs/network.md"] == b"# net"
    assert "estimate/latest.json" not in answers
    assert answers["engagements/_default_/_default_/estimate/latest.xlsx"] == b"xlsx"

    manifest = json.loads(raw["engagements/_default_/_default_/_engagement.json"])
    assert manifest["engagement"] == "_default_/_default_"
    assert manifest["visibility"] == "all"


def test_apply_is_idempotent(mig):
    m, svc, raw, answers = mig
    m.main(["--apply", "--skip-sql"])
    before = dict(raw), dict(answers)
    m.main(["--apply", "--skip-sql"])
    assert (raw, answers) == before
