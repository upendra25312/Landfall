"""Cycle 18 — engagement identity + per-engagement ADLS layout (E11.1 / E11.2)."""
import pytest

import engagement as eng


@pytest.mark.parametrize("raw, want", [
    ("Contoso Ltd.", "contoso-ltd"),
    ("  DC Exit 2027!  ", "dc-exit-2027"),
    ("Ürün / A&B", "urun-a-b"),
    ("", "x"),
    ("---", "x"),
    ("A" * 80, "a" * 40),
])
def test_slug(raw, want):
    assert eng.slug(raw) == want


def test_make_and_split_engagement_id():
    eid = eng.make_engagement_id("Contoso Ltd", "DC Exit 2027")
    assert eid == "contoso-ltd/dc-exit-2027"
    assert eng.split(eid) == ("contoso-ltd", "dc-exit-2027")


@pytest.mark.parametrize("eid, ok", [
    ("contoso/dc-exit", True),
    ("_default_/_default_", True),
    ("a/b/c", False),
    ("Contoso/x", False),          # uppercase
    ("-lead/x", False),            # leading hyphen
    ("/x", False),
    ("x", False),
    ("a" * 41 + "/b", False),
])
def test_valid_engagement_id(eid, ok):
    assert eng.valid_engagement_id(eid) is ok


def test_normalize_trims_and_rejects():
    assert eng.normalize_engagement("/contoso//dc-exit/") == "contoso/dc-exit"
    with pytest.raises(ValueError):
        eng.normalize_engagement("Contoso/DC Exit")


def test_blob_prefixes_are_engagement_scoped():
    e = "contoso/dc-exit"
    assert eng.inventory_prefix(e) == "engagements/contoso/dc-exit/inventory"
    assert eng.docs_prefix(e) == "engagements/contoso/dc-exit/docs"
    assert eng.engagement_file(e) == "engagements/contoso/dc-exit/_engagement.json"
    assert eng.estimate_prefix(e) == "engagements/contoso/dc-exit/estimate"
    assert eng.ingest_report_prefix(e) == "engagements/contoso/dc-exit/_ingest"
    assert eng.history_prefix(e, "2026-09-08T10-00-00Z").endswith(
        "/history/2026-09-08T10-00-00Z")


def test_parse_inventory_blob():
    assert eng.parse_inventory_blob(
        "engagements/contoso/dc-exit/inventory/servers.csv"
    ) == ("contoso/dc-exit", "servers.csv")
    # full Event Grid subject
    assert eng.parse_inventory_blob(
        "/blobServices/default/containers/raw/blobs/"
        "engagements/acme/move/docs/network.md"
    ) == ("acme/move", "network.md")
    # not an inventory/docs path
    assert eng.parse_inventory_blob("engagements/acme/move/_engagement.json") is None
    assert eng.parse_inventory_blob("raw/inventory/servers.csv") is None


def test_two_engagements_have_disjoint_prefixes():
    a = eng.answers_prefix("contoso/dc-exit")
    b = eng.answers_prefix("contoso/dc-exit-2")
    assert a != b and not b.startswith(a + "/")


def test_loader_scopes_by_engagement_and_source_file():
    """load() stamps engagement_id and keys the delete on (engagement_id, source_file)."""
    import ingest.loader as loader

    captured = {}

    class _Cur:
        def execute(self, sql, params=None):
            captured.setdefault("exec", []).append((sql, params))

        def executemany(self, sql, data):
            captured["insert_sql"] = sql
            captured["insert_data"] = data

    class _Conn:
        def cursor(self):
            return _Cur()

        def commit(self):
            captured["committed"] = True

        def close(self):
            captured["closed"] = True

    rows = [{"server_id": "s1", "vcpu": 2, "source_file": "servers.csv"},
            {"server_id": "s2", "vcpu": 4, "source_file": "servers.csv"}]
    n = loader.load("servers", rows, "contoso/dc-exit", conn=_Conn())
    assert n == 2
    # session context set first
    assert any("sp_set_session_context" in s for s, _ in captured["exec"])
    # delete keyed on engagement + source_file
    dels = [(s, p) for s, p in captured["exec"] if s.startswith("DELETE")]
    assert dels and dels[0][1] == ["contoso/dc-exit", "servers.csv"]
    # every inserted row carries engagement_id as the first column
    assert loader.TABLE_COLS["servers"][0] == "engagement_id"
    assert all(row[0] == "contoso/dc-exit" for row in captured["insert_data"])


def test_load_rejects_bad_engagement_before_db():
    import ingest.loader as loader
    with pytest.raises(ValueError):
        loader.load("servers", [{"server_id": "s1", "source_file": "x.csv"}],
                    "Bad Engagement", conn=object())
