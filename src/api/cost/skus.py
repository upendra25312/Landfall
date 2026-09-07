"""
Azure VM SKU catalogue + managed-disk tiers used by the right-sizer.

Small curated set — the v5 general-purpose / memory-optimised / compute-optimised
families and Premium SSD (v1) disk tiers. Enough to place a rehost estimate; the
cost tool (E2.2) prices whatever SKU lands here.
"""
CATALOG_VERSION = "2026-09"

# family -> [(sku, vCPU, RAM GiB)], ascending
SKUS: dict[str, list[tuple[str, int, int]]] = {
    "F": [  # compute-optimised, ~2 GiB/vCPU
        ("Standard_F2s_v2", 2, 4), ("Standard_F4s_v2", 4, 8), ("Standard_F8s_v2", 8, 16),
        ("Standard_F16s_v2", 16, 32), ("Standard_F32s_v2", 32, 64),
        ("Standard_F48s_v2", 48, 96), ("Standard_F64s_v2", 64, 128),
        ("Standard_F72s_v2", 72, 144),
    ],
    "D": [  # general purpose, 4 GiB/vCPU
        ("Standard_D2s_v5", 2, 8), ("Standard_D4s_v5", 4, 16), ("Standard_D8s_v5", 8, 32),
        ("Standard_D16s_v5", 16, 64), ("Standard_D32s_v5", 32, 128),
        ("Standard_D48s_v5", 48, 192), ("Standard_D64s_v5", 64, 256),
        ("Standard_D96s_v5", 96, 384),
    ],
    # memory-optimised incl. constrained-vCPU SKUs (full RAM, fewer BILLABLE vCPUs -
    # the right pick for a RAM-heavy DB box). Sorted by (billable vCPU, RAM).
    "E": [
        ("Standard_E2s_v5", 2, 16), ("Standard_E4-2s_v5", 2, 32), ("Standard_E8-2s_v5", 2, 64),
        ("Standard_E4s_v5", 4, 32), ("Standard_E8-4s_v5", 4, 64), ("Standard_E16-4s_v5", 4, 128),
        ("Standard_E8s_v5", 8, 64), ("Standard_E16-8s_v5", 8, 128), ("Standard_E32-8s_v5", 8, 256),
        ("Standard_E16s_v5", 16, 128), ("Standard_E32-16s_v5", 16, 256), ("Standard_E64-16s_v5", 16, 512),
        ("Standard_E20s_v5", 20, 160),
        ("Standard_E32s_v5", 32, 256), ("Standard_E64-32s_v5", 32, 512),
        ("Standard_E48s_v5", 48, 384), ("Standard_E96-48s_v5", 48, 672),
        ("Standard_E64s_v5", 64, 512), ("Standard_E96s_v5", 96, 672),
    ],
}
_MAX_RAM = {fam: rows[-1][2] for fam, rows in SKUS.items()}

# Premium SSD v1: (tier, size GiB, baseline provisioned IOPS)
DISK_TIERS: list[tuple[str, int, int]] = [
    ("P4", 32, 120), ("P6", 64, 240), ("P10", 128, 500), ("P15", 256, 1100),
    ("P20", 512, 2300), ("P30", 1024, 5000), ("P40", 2048, 7500),
    ("P50", 4096, 7500), ("P60", 8192, 16000), ("P70", 16384, 18000),
    ("P80", 32767, 20000),
]


def family_for(ram_per_vcpu: float) -> str:
    if ram_per_vcpu <= 2.5:
        return "F"
    if ram_per_vcpu <= 5.0:
        return "D"
    return "E"


def pick_sku(family: str, vcpu_need: float, ram_need: float) -> tuple[str, str, int, int, bool]:
    """Smallest SKU meeting BOTH dimensions. Returns (sku, family, vcpu, ram, capped)."""
    # bump family if the memory requirement won't fit
    order = [family] + [f for f in ("D", "E") if f != family]
    for fam in order:
        if ram_need <= _MAX_RAM[fam] or fam == "E":
            for sku, v, r in SKUS[fam]:
                if v >= vcpu_need - 1e-6 and r >= ram_need - 1e-6:
                    return sku, fam, v, r, False
            # nothing fits in this family -> try the next, else cap at the biggest
    sku, v, r = SKUS["E"][-1]
    return sku, "E", v, r, True


def disk_tier(size_gb: float | None, iops_peak: float | None) -> dict:
    size = size_gb or 32
    iops = iops_peak or 0
    for tier, cap_gib, cap_iops in DISK_TIERS:
        if cap_gib >= size and cap_iops >= iops:
            return {"tier": tier, "size_gib": cap_gib, "provisioned_iops": cap_iops}
    t, g, i = DISK_TIERS[-1]
    return {"tier": t, "size_gib": g, "provisioned_iops": i}
