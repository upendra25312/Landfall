"""C25b — adapter field mapping (offline; no browser).

These lock the tier/OS-conditional control names that the live 55-line POE run
flagged in `fields_not_set`: Linux VMs render no `osBillingOption` and a distro
`type`; Azure NetApp Files / Azure Files prefix their capacity controls with the
selected tier.
"""
import os
import sys

from conftest import ROOT

_CALC = os.path.join(ROOT, "src", "calc")
if _CALC not in sys.path:
    sys.path.append(_CALC)

from adapters import adapter_for  # noqa: E402


def _fields(service, config):
    ad = adapter_for(service)
    assert ad is not None, service
    return {name: (value, kind) for name, value, kind in ad["fields"](config)}


def test_linux_vm_has_distro_type_and_no_hybrid_benefit():
    f = _fields("virtual-machines", {"operatingSystem": "linux", "size": "d4sv5",
                                     "count": 3, "osBillingOption": "ahb",
                                     "computeBillingOption": "three-year"})
    assert f["operatingSystem"][0] == "linux"
    assert f["type"][0] == "ubuntu"          # not "os-only"
    assert "osBillingOption" not in f        # AHB is Windows/SQL only
    assert f["computeBillingOption"][0] == "three-year"


def test_linux_vm_maps_rhel_distro():
    f = _fields("virtual-machines", {"os": "RHEL", "size": "e8sv5", "count": 1})
    assert f["operatingSystem"][0] == "linux"
    assert f["type"][0] == "redhat"


def test_windows_vm_keeps_os_only_and_hybrid_benefit():
    f = _fields("virtual-machines", {"operatingSystem": "windows", "size": "d4sv5",
                                     "count": 2, "osBillingOption": "ahb"})
    assert f["type"][0] == "os-only"
    assert f["osBillingOption"] == ("ahb", "radio")


def test_anf_premium_tier_prefixes_capacity_controls():
    f = _fields("azure-netapp-files", {"service_level": "premium", "capacity_gb": 24576})
    assert f["tier"][0] == "premium-storage"
    assert "premiumUnits" in f and "premiumHours" in f
    assert "standardUnits" not in f
    assert f["premiumUnits"][0] == 24  # 24576 GiB / 1024


def test_anf_standard_tier_uses_bare_names():
    f = _fields("azure-netapp-files", {"service_level": "standard", "capacity_gb": 4096})
    assert "standardUnits" in f and "standardHours" in f


def test_azure_files_premium_uses_ssd_prefixed_v2_controls():
    f = _fields("azure-files", {"tier": "premium", "capacity_gb": 6144})
    assert f["performanceTier"][0] == "premium"
    assert f["billingModel"][0] == "provisionedv2"
    assert "ssdProvisionedV2StorageUnits" in f
    assert f["ssdProvisionedV2StorageUnits"] == (6144, "number")


def test_azure_files_standard_uses_bare_v2_controls():
    f = _fields("azure-files", {"tier": "standard", "capacity_gb": 2048})
    assert "provisionedV2StorageUnits" in f
    assert "ssdProvisionedV2StorageUnits" not in f


def test_bastion_premium_keeps_standard_outbound_prefix():
    f = _fields("azure-bastion", {"tier": "premium", "hours": 730, "outbound_data_gb": 10})
    assert f["premiumHours"][0] == 730
    assert "standardOutboundDataTransfer" in f
    assert "premiumOutboundDataTransfer" not in f
