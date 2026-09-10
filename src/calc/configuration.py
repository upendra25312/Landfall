"""Reject incomplete calculator configurations instead of exporting default prices."""


def validate_configuration(service, config, result):
    missing = list(result.get("missing", []))
    notes = []
    # The calculator omits Bastion transfer controls in some regions, but exports
    # its fixed 5 GB default. Exactly 5 GB is the documented free allowance:
    # https://azure.microsoft.com/en-us/pricing/details/azure-bastion/
    transfer = {"basicOutboundDataTransferFactor=1", "basicOutboundDataTransfer",
                "standardOutboundDataTransferFactor=1", "standardOutboundDataTransfer"}
    if (service == "azure-bastion" and missing and set(missing) <= transfer
            and float(config.get("outbound_data_gb", 5)) == 5):
        notes.append("Bastion transfer controls unavailable in this region; calculator's 5 GB default retained. "
                     "The requested 5 GB/month is within Microsoft's published free allowance.")
        missing = []
    if missing:
        raise ValueError(f"{service}: calculator configuration incomplete: {', '.join(missing)}")
    return notes
