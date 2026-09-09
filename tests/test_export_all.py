"""E9.5 — close-out export: enumerate every engagement, zip raw/ + answers/ (+ SQL),
never lose the blob export when SQL is down.
"""
import io
import os
import sys
import zipfile

import pytest
from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import export_all as ea  # noqa: E402


class _Blob:
    def __init__(self, name, data):
        self.name, self._d = name, data
        self.size = len(data)

    def readall(self):
        return self._d


class _Cont:
    def __init__(self, store):
        self.store = store

    def list_blobs(self, name_starts_with=""):
        return [_Blob(k, v) for k, v in sorted(self.store.items())
                if k.startswith(name_starts_with)]

    def download_blob(self, name):
        return _Blob(name, self.store[name])


class _Svc:
    def __init__(self, raw, ans):
        self._c = {"raw": _Cont(raw), "answers": _Cont(ans)}

    def get_container_client(self, name):
        return self._c[name]


@pytest.fixture()
def svc():
    raw = {
        "engagements/acme/dc-exit/_engagement.json": b'{"engagement":"acme/dc-exit"}',
        "engagements/acme/dc-exit/inventory/servers.csv": b"hostname,vcpu\na,2\n",
        "engagements/contoso/move/_engagement.json": b'{"engagement":"contoso/move"}',
        "engagements/contoso/move/inventory/x.csv": b"a,b\n1,2\n",
        "engagements/acme/dc-exit/.keep": b"",           # skipped
    }
    ans = {
        "engagements/acme/dc-exit/estimate/latest.json": b'{"meta":{}}',
        "engagements/acme/dc-exit/_chat.json": b'{"turns":[]}',
    }
    return _Svc(raw, ans)


def test_list_engagements_from_manifests(svc):
    assert ea.list_engagements(svc) == ["acme/dc-exit", "contoso/move"]


def test_export_one_zips_raw_and_answers_and_skips_empties(svc):
    r = ea.export_one(svc, "acme/dc-exit", with_sql=False)
    z = zipfile.ZipFile(io.BytesIO(r.pop("_data")))
    names = set(z.namelist())
    assert "raw/inventory/servers.csv" in names
    assert "answers/estimate/latest.json" in names and "answers/_chat.json" in names
    assert "export.json" in names
    assert not any(n.endswith(".keep") for n in names)
    assert "raw/_engagement.json" in names
    assert r["raw_files"] == 2 and r["answer_files"] == 2   # _engagement.json + servers.csv
    import json
    meta = json.loads(z.read("export.json"))
    assert meta["engagement"] == "acme/dc-exit" and meta["close_out"] is True


def test_sql_failure_does_not_lose_the_blob_export(svc, monkeypatch):
    def _boom(zf, eid):
        raise RuntimeError("Database 'x' is not currently available")

    monkeypatch.setattr(ea, "_sql_dump", _boom)
    r = ea.export_one(svc, "acme/dc-exit", with_sql=True)
    z = zipfile.ZipFile(io.BytesIO(r.pop("_data")))
    assert "raw/inventory/servers.csv" in z.namelist()      # blobs still there
    assert "sql/_ERROR.txt" in z.namelist()
    assert isinstance(r["sql_rows"], str) and r["sql_rows"].startswith("error:")


def test_main_dry_run_writes_nothing(svc, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ea, "_svc", lambda: svc)
    rc = ea.main(["--dry-run", "--out", str(tmp_path)])
    assert rc == 0
    assert not list(tmp_path.iterdir())
    assert "acme/dc-exit" in capsys.readouterr().out


def test_main_writes_one_zip_per_engagement(svc, monkeypatch, tmp_path):
    monkeypatch.setattr(ea, "_svc", lambda: svc)
    rc = ea.main(["--out", str(tmp_path)])
    assert rc == 0
    zips = sorted(p.name for p in tmp_path.glob("*.zip"))
    assert zips == ["acme__dc-exit.landfall.zip", "contoso__move.landfall.zip"]
    assert (tmp_path / "manifest.json").exists()
