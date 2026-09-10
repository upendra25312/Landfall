"""C54: V2 capacity mapping and explicit rejection of incomplete calculator prices."""
import sys
from pathlib import Path

import pytest
from conftest import ROOT
sys.path.append(str(Path(ROOT) / "src/calc"))
from adapters import adapter_for
from configuration import validate_configuration


def test_v2_gateway_capacity_and_transfer_are_separate_dimensions():
    fields = {name: value for name, value, _ in adapter_for("application-gateway")["fields"](
        {"capacity_units": 3, "hours": 100, "outbound_data_gb": 2048})}
    assert fields["computeUnits"] == 3 and fields["hours"] == 100
    assert fields["persistentConnections"] == fields["throughput"] == 0
    assert fields["units"] == 2048 and fields["storageUnits"] == "1"
    assert "instances" not in fields and "size" not in fields


@pytest.mark.parametrize("gb", [0, 4, 6, 20])
def test_unavailable_bastion_controls_cannot_change_requested_transfer_to_default(gb):
    with pytest.raises(ValueError, match="configuration incomplete"):
        validate_configuration("azure-bastion", {"outbound_data_gb": gb},
                               {"missing": ["standardOutboundDataTransfer"]})


def test_exact_bastion_free_default_is_a_disclosed_assumption():
    notes = validate_configuration("azure-bastion", {"outbound_data_gb": 5},
                                   {"missing": ["standardOutboundDataTransfer"]})
    assert notes and "5 GB" in notes[0]


def test_explicit_zero_bastion_transfer_is_not_replaced_by_five():
    fields = {name: value for name, value, _ in adapter_for("azure-bastion")["fields"]({"outbound_data_gb": 0})}
    assert fields["standardOutboundDataTransfer"] == 0


def test_wrong_region_or_gateway_control_cannot_produce_a_price():
    for missing in (["region=invalid"], ["computeUnits"]):
        with pytest.raises(ValueError):
            validate_configuration("application-gateway", {}, {"missing": missing})
