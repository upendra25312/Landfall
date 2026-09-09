"""
A deterministic synthetic price book for the back-test with **realistic
non-linearity** — unlike `evals/fixtures.py` (flat $/vCPU), so that three linear
costing methods agreeing is a real result, not an artefact of a linear book.

  * per-vCPU rate eases ~12% from the smallest to the largest SKU (volume curve)
  * family multipliers: F (compute-opt) 0.86, D (general) 1.00, E (memory-opt) 1.28
  * Windows adds a per-vCPU licence on top of the Linux compute rate
  * 1-yr RI = 0.63x PAYG, 3-yr RI = 0.44x  (broadly the published shape)
  * managed disk priced per tier from the catalogue GiB size
"""
from __future__ import annotations

from cost.skus import DISK_TIERS, SKUS

_BASE_LINUX_VCPU_HR = 0.050          # D-family, smallest SKU, PAYG, Linux
_WINDOWS_LICENCE_VCPU_HR = 0.046     # added for Windows without AHB
_FAMILY_MULT = {"F": 0.86, "D": 1.00, "E": 1.28, "L": 1.10, "M": 1.9, "N": 3.0}
_RI = {"ri1y": 0.63, "ri3y": 0.44}


def _vcpu_curve(vcpu: int) -> float:
    """1.0 at 2 vCPU easing to ~0.88 at 64 vCPU."""
    return 1.0 - 0.12 * min(1.0, (vcpu - 2) / 62)


def price_book() -> dict:
    b: dict = {}
    for fam, rows in SKUS.items():
        mult = _FAMILY_MULT.get(fam, 1.0)
        for sku, vcpu, _ram in rows:
            lin_h = _BASE_LINUX_VCPU_HR * vcpu * mult * _vcpu_curve(vcpu)
            win_h = lin_h + _WINDOWS_LICENCE_VCPU_HR * vcpu
            b[sku] = {
                "linux": {"payg": round(lin_h, 5),
                          "ri1y": round(lin_h * _RI["ri1y"], 5),
                          "ri3y": round(lin_h * _RI["ri3y"], 5)},
                "windows": {"payg": round(win_h, 5),
                            # RI covers compute only, not the licence
                            "ri1y": round(lin_h * _RI["ri1y"] + _WINDOWS_LICENCE_VCPU_HR * vcpu, 5),
                            "ri3y": round(lin_h * _RI["ri3y"] + _WINDOWS_LICENCE_VCPU_HR * vcpu, 5)},
            }
    return b


def disk_book() -> dict:
    # Premium SSD v1 — larger tiers a touch cheaper per GiB
    out = {}
    for tier, gib, _iops in DISK_TIERS:
        per_gib = 0.12 * (1.0 - 0.15 * min(1.0, gib / 4096))
        out[tier] = round(gib * per_gib, 2)
    return out


def storage_rates() -> dict:
    return {
        "files_premium": 0.16, "files_standard_hot": 0.06,
        "anf_standard": 0.15, "anf_premium": 0.29, "anf_ultra": 0.39,
        "db_sql_mi": 0.13, "db_sql_hyperscale": 0.11, "db_flex_postgresql": 0.115,
        "db_flex_mysql": 0.115, "db_oracle": 0.16,
        "blob_hot_lrs": 0.018, "blob_cool_lrs": 0.01, "managed_premium_ssd_v2": 0.08,
    }


def books() -> tuple[dict, dict, dict]:
    return price_book(), disk_book(), storage_rates()
