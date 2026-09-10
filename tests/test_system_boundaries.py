"""C53 negative integration cases across real routers and in-memory storage."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from browser.serve import _Store


@pytest.fixture
def system(monkeypatch):
    import app
    import web_storage
    raw, answers = _Store(), _Store()
    for eid, owner, visibility in (("alice/private", "alice", "owner"),
                                   ("bob/empty", "bob", "owner"),
                                   ("_default_/_default_", "alice", "owner")):
        raw.put(f"engagements/{eid}/_engagement.json", json.dumps({
            "engagement": eid, "created_by": owner, "visibility": visibility,
        }).encode())
    answers.put("engagements/_default_/_default_/estimate/latest.json", b'{"private": "alice"}')
    answers.put("engagements/_default_/_default_/estimate/latest.xlsx", b"DEFAULT-PRIVATE")
    monkeypatch.setattr(web_storage, "_raw_container", lambda: raw)
    monkeypatch.setattr(web_storage, "_estimate_container", lambda: answers)
    return TestClient(app.app, headers={"x-ms-client-principal-name": "bob"}), raw, answers


@pytest.mark.parametrize("path", ["/dashboard/data", "/dashboard/download/xlsx",
                                 "/dashboard/landing-zone", "/dashboard/landing-zone-diagram"])
def test_missing_scoped_artifact_does_not_fall_back_to_default(system, path):
    client, _, answers = system
    answers.put("engagements/_default_/_default_/estimate/landing_zone.json", b"{}")
    answers.put("engagements/_default_/_default_/estimate/landing_zone.svg", b"<svg/>")
    response = client.get(path, params={"e": "bob/empty"})
    assert response.status_code == 404


@pytest.mark.parametrize("eid", ["missing/project", "../alice/private", "_default_/_default_", ""])
def test_unknown_malformed_or_denied_default_scope_is_not_readable(system, eid):
    client, _, _ = system
    assert client.get("/dashboard/data", params={"e": eid}).status_code in (403, 404)


def test_manifest_storage_failure_fails_closed(system, monkeypatch):
    client, raw, answers = system
    answers.put("engagements/bob/empty/estimate/latest.json", b'{"secret": 1}')
    monkeypatch.setattr(raw, "download_blob", lambda *_: (_ for _ in ()).throw(RuntimeError("storage unavailable")))
    assert client.get("/dashboard/data?e=bob/empty").status_code in (404, 503)


def test_specific_poe_download_dispatches_to_calculator_artifact(system):
    client, _, answers = system
    answers.put("engagements/bob/empty/estimate/landing_zone.xlsx", b"CALCULATOR-EXCEL")
    response = client.get("/dashboard/download/landing-zone-xlsx?e=bob/empty")
    assert response.status_code == 200, response.text
    assert response.content == b"CALCULATOR-EXCEL"
    assert "POE.xlsx" in response.headers["content-disposition"]


def archive(eid="alice/private", members=None, manifest=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as out:
        out.writestr("export.json", json.dumps({"engagement": eid, "format": "landfall-engagement/1"}))
        out.writestr("raw/_engagement.json", json.dumps(manifest or {
            "engagement": eid, "created_by": "mallory", "visibility": "all"}))
        for name, data in members or [("raw/inventory/servers.csv", b"hostname,vcpu\nx,2\n")]:
            out.writestr(name, data)
    return stream.getvalue()


def upload(client, payload, **kwargs):
    return client.post("/api/engagements/import", files={"file": ("test.zip", payload, "application/zip")}, **kwargs)


def test_import_cannot_overwrite_another_owners_engagement(system):
    client, raw, _ = system
    before = dict(raw.d)
    response = upload(client, archive(), data={"overwrite": "true"})
    assert response.status_code in (403, 404)
    assert raw.d == before


def test_import_preserves_existing_owner_and_visibility(system):
    client, raw, _ = system
    response = upload(client, archive("bob/empty"), data={"overwrite": "true"})
    assert response.status_code == 201
    saved = json.loads(raw.get("engagements/bob/empty/_engagement.json"))
    assert saved["created_by"] == "bob" and saved["visibility"] == "owner"


def test_new_import_binds_owner_to_caller(system):
    client, raw, _ = system
    assert upload(client, archive("new/project")).status_code == 201
    saved = json.loads(raw.get("engagements/new/project/_engagement.json"))
    assert saved["created_by"] == "bob" and saved["visibility"] == "owner"


@pytest.mark.parametrize("member", ["raw/../escape", "raw/inventory/../../escape", "raw/\\escape",
                                   "raw//escape", "unexpected/file"])
def test_unsafe_zip_is_rejected_before_any_write(system, member):
    client, raw, answers = system
    before = dict(raw.d), dict(answers.d)
    response = upload(client, archive("new/project", [(member, b"bad")]))
    assert response.status_code == 400
    assert (raw.d, answers.d) == before


def test_expanded_archive_limit_applies_before_writes(system, monkeypatch):
    from routes import transfers
    client, raw, _ = system
    monkeypatch.setattr(transfers, "_EXPORT_MAX", 2000)
    before = dict(raw.d)
    response = upload(client, archive("new/project", [("raw/docs/large.txt", b"x" * 10000)]))
    assert response.status_code == 413
    assert raw.d == before


def test_import_requires_an_authenticated_principal(system):
    client, raw, _ = system
    client.headers.pop("x-ms-client-principal-name")
    before = dict(raw.d)
    assert upload(client, archive("new/project")).status_code == 401
    assert raw.d == before


def test_duplicate_archive_members_are_rejected_before_writes(system):
    client, raw, answers = system
    before = dict(raw.d), dict(answers.d)
    with pytest.warns(UserWarning, match="Duplicate name"):
        payload = archive("new/project", [("raw/docs/a.txt", b"one"), ("raw/docs/a.txt", b"two")])
    assert upload(client, payload).status_code == 400
    assert (raw.d, answers.d) == before


def test_archive_manifest_cannot_name_a_different_engagement(system):
    client, raw, _ = system
    before = dict(raw.d)
    assert upload(client, archive("new/project", manifest={"engagement": "alice/private"})).status_code == 400
    assert raw.d == before


def test_failed_storage_write_is_not_reported_as_success(system, monkeypatch):
    client, raw, _ = system
    monkeypatch.setattr(raw, "upload_blob", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("unavailable")))
    response = upload(client, archive("new/project"))
    assert response.status_code == 503
    assert response.json()["imported"] == 0


def test_sql_backup_is_explicitly_reported_as_not_restored(system):
    client, _, _ = system
    response = upload(client, archive("new/project", [("sql/servers.json", b"[]")]))
    assert response.status_code == 201
    assert response.json()["not_imported"] == ["sql/servers.json"]


def test_concurrent_engagement_creation_cannot_be_overwritten_by_import(system, monkeypatch):
    from azure.core.exceptions import ResourceExistsError
    client, raw, _ = system
    upload_blob = raw.upload_blob
    def concurrent_create(key, data, overwrite=True, **kwargs):
        if key.endswith("/_engagement.json") and not overwrite:
            # Another principal won the conditional create after our absence read.
            raise ResourceExistsError("another owner created this engagement")
        return upload_blob(key, data, overwrite=overwrite, **kwargs)
    monkeypatch.setattr(raw, "upload_blob", concurrent_create)
    before = dict(raw.d)
    response = upload(client, archive("new/project"))
    assert response.status_code == 409
    assert raw.d == before
