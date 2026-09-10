"""Cycle 7 — design_landing_zone (E3.1 / E3.2 / E3.3). Deterministic, pure."""
import csv
import io

from conftest import sample_bytes

from cost.config import load_config
from lz.design import assign_zone, design_landing_zone


def _cfg(**lz):
    lz.setdefault("org_id", "alz")             # pin — don't inherit the repo config's org
    return load_config(overrides={"landing_zone": lz})


CORP = {"app_id": "a1", "app_name": "HR", "criticality": 2, "internet_facing": 0,
        "compliance_scope": ""}
ONLINE = {"app_id": "a2", "app_name": "Shop", "criticality": 1, "internet_facing": 1,
          "compliance_scope": ""}
PCI = {"app_id": "a3", "app_name": "Pay", "criticality": 1, "internet_facing": 1,
       "compliance_scope": "PCI-DSS"}
SOX = {"app_id": "a4", "app_name": "Ledger", "criticality": 2, "internet_facing": 0,
       "compliance_scope": "SOX"}


def test_zone_assignment_rules():
    reg = {"PCI-DSS", "HIPAA"}
    assert assign_zone(CORP, reg) == ("corp", None)
    assert assign_zone(ONLINE, reg) == ("online", None)
    assert assign_zone(PCI, reg) == ("regulated", "PCI-DSS")
    # SOX is not in the regulated set -> stays corp (policy still covers it via baseline)
    assert assign_zone(SOX, reg) == ("corp", None)


def test_no_regulated_app_means_no_regulated_spoke():
    r = design_landing_zone([CORP, ONLINE], None, _cfg())
    assert r["regulated"] is False
    assert r["regulated_scopes_present"] == []
    assert not any(s["zone"] == "regulated" for s in r["spokes"])
    assert "alz-confidential" not in r["management_groups"]["alz"]["alz-landingzones"]


def test_regulated_app_creates_spoke_mg_and_policy_overlay():
    r = design_landing_zone([CORP, ONLINE, PCI], None, _cfg())
    assert r["regulated"] is True
    assert r["regulated_scopes_present"] == ["PCI-DSS"]
    reg_spokes = [s["name"] for s in r["spokes"] if s["zone"] == "regulated"]
    assert reg_spokes == ["pcidss-prod", "pcidss-nonprod"]
    assert "alz-confidential" in r["management_groups"]["alz"]["alz-landingzones"]
    assert any("PCI DSS v4" in p for p in r["policy"]["regulated_overlay"])
    assert any("Customer-managed keys" in p for p in r["policy"]["regulated_overlay"])


def test_swapping_portfolio_changes_topology():
    small = design_landing_zone([CORP], None, _cfg())
    big = design_landing_zone([CORP, ONLINE, PCI], None, _cfg())
    assert len(big["spokes"]) > len(small["spokes"])
    assert "online" not in small["zone_counts"]
    assert "online" in big["zone_counts"]


def test_ip_plan_blocks_are_non_overlapping_and_in_supernet():
    import ipaddress
    r = design_landing_zone([CORP, ONLINE, PCI], None, _cfg(ip_supernet="10.50.0.0/16"))
    super_net = ipaddress.ip_network("10.50.0.0/16")
    nets = [ipaddress.ip_network(v) for k, v in r["ip_plan"].items()
            if k not in ("supernet", "dr_supernet")]
    for n in nets:
        assert n.subnet_of(super_net)
    for i, a in enumerate(nets):
        for b in nets[i + 1:]:
            assert not a.overlaps(b)


def test_resiliency_tier_from_criticality():
    r = design_landing_zone([PCI, SOX, {"app_id": "a5", "criticality": 4,
                                        "internet_facing": 0, "compliance_scope": ""}], None, _cfg())
    by_app = {p["app_id"]: p["resiliency_tier"] for p in r["applications_placed"]}
    assert by_app["a3"] == "1" and by_app["a4"] == "2" and by_app["a5"] == "4"
    assert r["dr"]["apps_by_tier"] == {"1": 1, "2": 1, "4": 1}


def test_identity_model_switch():
    ad = design_landing_zone([CORP], None, _cfg(identity_model="extend_ad"))
    entra = design_landing_zone([CORP], None, _cfg(identity_model="greenfield_entra"))
    assert "Domain Controllers" in " ".join(ad["hub"]["components"])
    assert "Domain Controllers" not in " ".join(entra["hub"]["components"])
    assert entra["identity"]["model"] == "Greenfield Entra ID"


def test_deterministic_over_sample_portfolio():
    apps = list(csv.DictReader(io.StringIO(sample_bytes("applications.csv").decode("utf-8-sig"))))
    ss = {"total_servers": 250, "by_env": {"prod": 173, "nonprod": 47, "dev": 27, "dr": 3},
          "total_vcpu": 1940, "os_families": {"windows": 150, "linux": 100}}
    a = design_landing_zone(apps, ss, load_config())
    b = design_landing_zone(apps, ss, load_config())
    assert a == b
    # sample has PCI-DSS (4), HIPAA (1) — both in the default regulated set; SOX/GDPR are not
    assert set(a["regulated_scopes_present"]) == {"PCI-DSS", "HIPAA"}
    assert a["regulated"] is True
    assert a["server_footprint"]["total_servers"] == 250
