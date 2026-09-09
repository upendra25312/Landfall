"""C29 / E1.7 — per-engagement _mapping.json column-mapping override."""
from conftest import fixture_bytes, sample_bytes

from ingest.core import match_mapping, normalize


# --- match_mapping resolution --------------------------------------------

def test_flat_override_applies_to_every_file():
    m = {"$comment": "x", "profile": "landfall_servers", "columns": {"vcpu": "CPU Cores"}}
    ov = match_mapping(m, "anything.csv")
    assert ov["profile"] == "landfall_servers" and ov["columns"]["vcpu"] == "CPU Cores"


def test_per_file_map_matches_exact_then_glob():
    m = {"files": {"servers.csv": {"profile": "landfall_servers"},
                   "*.xlsx": {"profile": "rvtools_vinfo"}}}
    assert match_mapping(m, "servers.csv")["profile"] == "landfall_servers"
    assert match_mapping(m, "client_export.xlsx")["profile"] == "rvtools_vinfo"
    assert match_mapping(m, "deps.csv") is None


def test_no_mapping_is_none():
    assert match_mapping(None, "x.csv") is None
    assert match_mapping({}, "x.csv") is None


# --- normalize with an override ----------------------------------------

def test_override_pins_a_profile_for_an_ambiguous_file():
    data = fixture_bytes("rvtools_vinfo.csv")
    plain = normalize("mystery.csv", data)
    pinned = normalize("mystery.csv", data, {"profile": "rvtools_vinfo"})
    assert pinned.table == "servers" and pinned.profile == "rvtools_vinfo"
    assert any("pinned" in n for n in pinned.mapping_notes)


def test_unknown_profile_name_is_ignored_with_a_note():
    res = normalize("servers.csv", sample_bytes("servers.csv"), {"profile": "not_a_profile"})
    assert res.table == "servers"                     # detection still worked
    assert any("unknown profile" in n for n in res.mapping_notes)


def test_column_remap_recovers_a_misnamed_header():
    csv_bytes = (b"hostname,CPU Cores,Memory GB,env\n"
                 b"web01,8,32,prod\nweb02,4,16,test\n")
    # headers 'CPU Cores' / 'Memory GB' don't match any profile on their own
    assert normalize("servers.csv", csv_bytes).table is None
    fixed = normalize("servers.csv", csv_bytes,
                      {"profile": "landfall_servers",
                       "columns": {"vcpu": "CPU Cores", "ram_gb": "Memory GB"}})
    assert fixed.table == "servers"
    assert fixed.rows[0]["vcpu"] == 8 and fixed.rows[0]["ram_gb"] == 32
    assert any("vcpu" in n for n in fixed.mapping_notes)


def test_override_flags_a_header_that_is_not_present():
    res = normalize("servers.csv", sample_bytes("servers.csv"),
                    {"columns": {"vcpu": "Totally Missing Column"}})
    assert any("header not present" in n for n in res.mapping_notes)
