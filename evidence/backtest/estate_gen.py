"""
Deterministic synthetic estates for the E10.1 back-test.

`build_estate(preset)` returns dicts (servers / applications / dependencies /
storage) whose keys match `scripts/schema.sql`, the same shape the ingestion
pipeline produces. Three presets of deliberately different size and mix:

    small        ~40 servers, one line of business, no compliance, thin perf data
    midmarket    ~230 servers, mixed OS, PCI + HIPAA, ~70% monitored
    enterprise   ~620 servers, DB-heavy, PCI + HIPAA + SOX, well monitored

Seeded per preset — the same preset always yields the same estate. This is not
the production `sample-estate/generate_estate.py` (that one models one specific
client); this is a small spread of estates to test that three costing methods
agree on each.
"""
from __future__ import annotations

import random

_WIN_OS = [("Windows Server", "2012 R2", "2023-10-10"),
           ("Windows Server", "2016", "2027-01-12"),
           ("Windows Server", "2019", "2029-01-09"),
           ("Windows Server", "2022", "2031-10-14")]
_LIN_OS = [("Red Hat Enterprise Linux", "7.9", "2024-06-30"),
           ("Red Hat Enterprise Linux", "8.8", "2029-05-31"),
           ("Ubuntu", "20.04 LTS", "2025-04-30"),
           ("Ubuntu", "22.04 LTS", "2027-04-30"),
           ("SUSE Linux Enterprise Server", "15 SP4", "2031-12-31")]

# (vcpu, ram_gb) with weight — a realistic long tail
_SIZES = [((2, 8), 0.16), ((2, 16), 0.12), ((4, 16), 0.20), ((4, 32), 0.14),
          ((8, 32), 0.15), ((8, 64), 0.09), ((16, 64), 0.07), ((16, 128), 0.04),
          ((32, 128), 0.02), ((32, 256), 0.01)]

_ENVS = [("prod", 0.55), ("nonprod", 0.25), ("dev", 0.14), ("dr", 0.06)]

_PRESETS = {
    "small":      dict(seed=301, servers=40,  win_frac=0.55, monitored=0.45,
                       compliance=[], db_frac=0.12, region="swedencentral"),
    "midmarket":  dict(seed=302, servers=230, win_frac=0.60, monitored=0.70,
                       compliance=["PCI-DSS", "HIPAA"], db_frac=0.18, region="swedencentral"),
    "enterprise": dict(seed=303, servers=620, win_frac=0.52, monitored=0.82,
                       compliance=["PCI-DSS", "HIPAA", "SOX"], db_frac=0.24, region="eastus2"),
}

PRESETS = tuple(_PRESETS)


def _wchoice(rng, pairs):
    items = [i for i, _ in pairs]
    return rng.choices(items, weights=[w for _, w in pairs], k=1)[0]


def build_estate(preset: str) -> dict:
    if preset not in _PRESETS:
        raise ValueError(f"unknown preset {preset!r}; pick from {PRESETS}")
    p = _PRESETS[preset]
    rng = random.Random(p["seed"])
    n = p["servers"]

    n_apps = max(3, round(n / 9))
    apps = []
    for i in range(1, n_apps + 1):
        comp = "None"
        if p["compliance"] and rng.random() < 0.28:
            comp = rng.choice(p["compliance"])
        apps.append({
            "app_id": f"{preset}-app-{i:03d}",
            "app_name": f"{preset.title()} App {i}",
            "business_owner": f"Owner {1 + i % 7}",
            "criticality": rng.choice([1, 2, 2, 3, 3, 3, 4]),
            "users": rng.choice([0, 25, 120, 600, 3000, 40000]),
            "tech_stack": rng.choice(["IIS 10 / .NET 4.8", "NGINX / Node 18",
                                      "Tomcat 9 / OpenJDK 11", "Spring Boot / OpenJDK 17",
                                      "PostgreSQL 14", "SQL Server 2019", "Oracle 19c"]),
            "db_engine": "", "internet_facing": 1 if rng.random() < 0.25 else 0,
            "compliance_scope": comp, "disposition": "", "complexity": "", "wave": "",
        })

    servers, storage = [], []
    st_seq = 0
    for i in range(1, n + 1):
        sid = f"{preset}-srv-{i:04d}"
        is_win = rng.random() < p["win_frac"]
        os_name, os_ver, eol = rng.choice(_WIN_OS if is_win else _LIN_OS)
        env = _wchoice(rng, _ENVS)
        (vcpu, ram) = _wchoice(rng, _SIZES)
        is_db = rng.random() < p["db_frac"]
        if is_db:
            vcpu = min(64, vcpu * 2)
            ram = min(512, ram * 2)
        prov = rng.choice([80, 128, 200, 256, 400, 512, 1024]) + (1024 if is_db else 0)
        used = round(prov * rng.uniform(0.30, 0.82), 1)

        if rng.random() < p["monitored"]:
            # sustained-busy well under capacity — the usual over-provisioned estate
            cpu_p95 = round(rng.uniform(6, 38), 1)
            ram_p95 = round(rng.uniform(28, 72), 1)
            cpu_avg = round(cpu_p95 * rng.uniform(0.55, 0.85), 1)
            ram_avg = round(ram_p95 * rng.uniform(0.8, 0.95), 1)
        else:
            cpu_p95 = ram_p95 = cpu_avg = ram_avg = ""

        app = apps[rng.randrange(n_apps)]
        servers.append({
            "server_id": sid, "hostname": sid, "env": env,
            "os_name": os_name, "os_version": os_ver, "os_eol_date": eol,
            "vcpu": vcpu, "ram_gb": ram,
            "provisioned_disk_gb": prov, "used_disk_gb": used,
            "cpu_avg_pct": cpu_avg, "cpu_peak_pct": "", "cpu_p95_pct": cpu_p95,
            "ram_avg_pct": ram_avg, "ram_p95_pct": ram_p95,
            "disk_iops_avg": "", "disk_iops_peak": rng.choice([500, 1100, 2300, 5000]),
            "net_in_gb_30d": round(rng.uniform(5, 400), 1),
            "net_out_gb_30d": round(rng.uniform(5, 1200), 1),
            "cluster": f"{preset[:3].upper()}-CL{1 + i % 4}", "datacenter": "DC-1",
            "powerstate": "poweredOn" if rng.random() < 0.94 else "poweredOff",
            "app_id": app["app_id"], "notes": "",
        })

        st_seq += 1
        storage.append({"storage_id": f"{preset}-stg-{st_seq:05d}", "server_id": sid,
                        "type": "block", "size_gb": 128 if is_win else 64,
                        "iops": 500, "target_service": "Premium SSD P10"})
        if is_db:
            st_seq += 1
            storage.append({"storage_id": f"{preset}-stg-{st_seq:05d}", "server_id": sid,
                            "type": "db", "size_gb": round(prov * rng.uniform(0.4, 0.9), 1),
                            "iops": 5000,
                            "target_service": rng.choice(["SQL Managed Instance",
                                                          "Azure SQL DB Hyperscale",
                                                          "PostgreSQL Flexible Server"])})

    # a few shared file shares
    for k in range(max(1, n // 200)):
        st_seq += 1
        storage.append({"storage_id": f"{preset}-stg-{st_seq:05d}",
                        "server_id": servers[k]["server_id"], "type": "file",
                        "size_gb": rng.choice([2048, 4096, 8192]), "iops": 3000,
                        "target_service": "Azure Files Premium"})

    # light dependency graph — app tiers to their own DBs (enough for plan_waves)
    deps = []
    by_app: dict[str, list[str]] = {}
    for s in servers:
        by_app.setdefault(s["app_id"], []).append(s["server_id"])
    for aid, sids in by_app.items():
        for a, b in zip(sids, sids[1:]):
            deps.append({"src_id": a, "dst_id": b, "port": 1433, "protocol": "TDS",
                         "direction": "outbound", "confidence": "high",
                         "bytes_30d_gb": 120, "flows_30d": 500000, "last_seen": "2026-09-05"})

    return {"preset": preset, "region": p["region"], "compliance": p["compliance"],
            "servers": servers, "applications": apps, "dependencies": deps, "storage": storage}


def estate_profile(estate: dict) -> dict:
    s = estate["servers"]
    on = [x for x in s if (x.get("powerstate") or "").lower() != "poweredoff"]
    monitored = sum(1 for x in s if x.get("cpu_p95_pct") not in ("", None))
    return {
        "preset": estate["preset"], "region": estate["region"],
        "servers": len(s), "powered_on": len(on),
        "applications": len(estate["applications"]),
        "monitored_pct": round(100 * monitored / len(s)),
        "total_vcpu": sum(int(x["vcpu"]) for x in s),
        "total_ram_gb": sum(int(x["ram_gb"]) for x in s),
        "storage_volumes": len(estate["storage"]),
        "compliance": estate["compliance"],
    }
