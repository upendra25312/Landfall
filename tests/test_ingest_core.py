"""Cycle 1 — ingestion core: detection, mapping, unit normalisation, id synthesis."""
from conftest import fixture_bytes, sample_bytes

from ingest.core import normalize, detect_profile, read_table


def test_native_servers_detected_and_identity_mapped():
    res = normalize("servers.csv", sample_bytes("servers.csv"))
    assert res.profile == "landfall_servers"
    assert res.table == "servers"
    assert res.row_count_in == 250
    assert len(res.rows) == 250
    r0 = res.rows[0]
    assert r0["server_id"] and r0["vcpu"] is not None
    assert r0["source_file"] == "servers.csv"
    assert not [i for i in res.issues if i.level == "error"]


def test_native_applications_and_dependencies_and_storage():
    for fname, prof, table in (
        ("applications.csv", "landfall_applications", "applications"),
        ("dependencies.csv", "landfall_dependencies", "dependencies"),
        ("storage.csv", "landfall_storage", "storage"),
    ):
        res = normalize(fname, sample_bytes(fname))
        assert (res.profile, res.table) == (prof, table), fname


def test_rvtools_vinfo_mapped_with_unit_conversion():
    res = normalize("client_rvtools_export.csv", fixture_bytes("rvtools_vinfo.csv"))
    assert res.profile == "rvtools_vinfo"
    assert res.table == "servers"
    by_host = {r["hostname"]: r for r in res.rows}
    web = by_host["web01"]
    assert web["vcpu"] == 4
    assert web["ram_gb"] == 16.0                       # 16384 MiB -> GiB
    assert web["provisioned_disk_gb"] == 200.0         # 204800 MiB -> GiB
    assert web["os_name"] == "Windows Server"
    assert web["os_version"] == "2019"
    assert by_host["app01"]["powerstate"] == "poweredOff"
    assert by_host["db01"]["os_name"] == "Red Hat Enterprise Linux"


def test_rvtools_rows_get_a_synthesised_server_id():
    res = normalize("rv.csv", fixture_bytes("rvtools_vinfo.csv"))
    ids = {r["server_id"] for r in res.rows}
    assert ids == {"web01", "db01", "app01", "legacy02"}  # falls back to hostname


def test_unrecognised_file_loads_nothing_and_reports_an_error():
    res = normalize("mystery.csv", fixture_bytes("unknown.csv"))
    assert res.table is None
    assert res.rows == []
    assert any(i.level == "error" for i in res.issues)


def test_detect_by_filename_hint_when_headers_are_ambiguous():
    headers, _ = read_table("servers.csv", sample_bytes("servers.csv"))
    assert detect_profile("acme-server-inventory.csv", headers).name == "landfall_servers"


def test_xlsx_reading_roundtrips(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "vInfo"
    ws.append(["VM", "Powerstate", "CPUs", "Memory", "OS according to the configuration file"])
    ws.append(["h1", "poweredOn", 2, 4096, "Ubuntu Linux (64-bit)"])
    p = tmp_path / "rv.xlsx"
    wb.save(p)
    res = normalize("rv.xlsx", p.read_bytes())
    assert res.profile == "rvtools_vinfo"
    assert res.rows[0]["ram_gb"] == 4.0
