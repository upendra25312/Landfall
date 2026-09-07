"""
Generate a synthetic "client estate" for the Landfall migration-estimate agent:
250 VMware VMs (150 Windows, 100 Linux), the business applications they host, the
network dependencies between them, and their storage - everything the assessment
tables in scripts/schema.sql expect.

Deterministic (seeded). Writes CSVs whose headers match the SQL columns exactly:
  servers.csv  applications.csv  dependencies.csv  storage.csv  performance.csv

servers.csv carries 30-day utilisation rollups (CPU/RAM %, disk IOPS, network in/out GB);
performance.csv is the daily series behind them (one row per monitored server per day);
dependencies.csv carries observed 30-day flow metrics (bytes, connection count, last seen).

    python sample-estate/generate_estate.py

Load with sample-estate/load_estate.py (or bcp / Data Studio).
"""
import csv
import os
import random
from datetime import date

random.seed(42)
HERE = os.path.dirname(__file__)

# ----------------------------------------------------------------------------
# reference data
# ----------------------------------------------------------------------------
DATACENTERS = ["DC-ASHBURN", "DC-DALLAS", "DC-DR-RENO"]
DC_WEIGHT = [0.5, 0.42, 0.08]

CLUSTERS = {
    "DC-ASHBURN": ["ASH-PRD-CL01", "ASH-PRD-CL02", "ASH-NPD-CL01"],
    "DC-DALLAS": ["DAL-PRD-CL01", "DAL-NPD-CL01", "DAL-DEV-CL01"],
    "DC-DR-RENO": ["RNO-DR-CL01"],
}

# os_name, os_version, os_eol_date (support end), weight
WINDOWS_OS = [
    ("Windows Server", "2012 R2", "2023-10-10", 0.18),
    ("Windows Server", "2016", "2027-01-12", 0.30),
    ("Windows Server", "2019", "2029-01-09", 0.37),
    ("Windows Server", "2022", "2031-10-14", 0.15),
]
LINUX_OS = [
    ("Red Hat Enterprise Linux", "7.9", "2024-06-30", 0.22),
    ("Red Hat Enterprise Linux", "8.8", "2029-05-31", 0.24),
    ("Red Hat Enterprise Linux", "9.3", "2032-05-31", 0.14),
    ("Ubuntu", "18.04 LTS", "2023-05-31", 0.10),
    ("Ubuntu", "20.04 LTS", "2025-04-30", 0.14),
    ("Ubuntu", "22.04 LTS", "2027-04-30", 0.10),
    ("SUSE Linux Enterprise Server", "15 SP4", "2031-12-31", 0.06),
]

SIZES = [  # vcpu, ram_gb typical
    (2, 8), (2, 16), (4, 16), (4, 32), (8, 32), (8, 64),
    (16, 64), (16, 128), (32, 128), (32, 256),
]
SIZE_WEIGHT = [0.14, 0.12, 0.20, 0.14, 0.15, 0.09, 0.08, 0.04, 0.03, 0.01]

ENVS = ["prod", "nonprod", "dev", "dr"]
ENV_WEIGHT = [0.55, 0.25, 0.14, 0.06]

WIN_STACKS = [
    ("IIS 10 / .NET Framework 4.8", None),
    ("IIS 10 / ASP.NET Core 6", None),
    ("Windows Service / .NET Framework 4.7.2", None),
    ("SQL Server 2016 Standard", "SQL Server 2016"),
    ("SQL Server 2019 Enterprise", "SQL Server 2019"),
    ("Microsoft SharePoint 2016", "SQL Server 2016"),
    ("BizTalk Server 2016", "SQL Server 2016"),
]
LINUX_STACKS = [
    ("Apache HTTPD 2.4 / PHP 7.4", None),
    ("NGINX 1.20 / Node.js 18", None),
    ("Apache Tomcat 9 / OpenJDK 11", None),
    ("Spring Boot / OpenJDK 17", None),
    ("PostgreSQL 13", "PostgreSQL 13"),
    ("MySQL 5.7", "MySQL 5.7"),
    ("Oracle Database 19c", "Oracle 19c"),
    ("MongoDB 4.4", "MongoDB 4.4"),
    ("RabbitMQ 3.9", None),
    ("HAProxy 2.4", None),
]

COMPLIANCE = ["None", "None", "None", "PCI-DSS", "SOX", "HIPAA", "GDPR"]
OWNERS = [
    "A. Okafor (Retail Platforms)", "M. Rossi (Finance Systems)",
    "K. Nguyen (Digital Channels)", "S. Patel (Data & Analytics)",
    "L. Andersson (Corporate IT)", "R. Gomez (Supply Chain IT)",
    "T. Brown (HR Technology)", "J. Kim (Security Engineering)",
]

# business applications: (name, tier_plan, criticality, users, internet_facing, compliance)
# tier_plan: list of (role, count, os) - os in {"win","lin","any"}
APP_DEFS = [
    ("Ecommerce Storefront",      [("web", 4, "lin"), ("app", 4, "lin"), ("db", 2, "lin")], 1, 210000, 1, "PCI-DSS"),
    ("Payment Gateway",           [("app", 3, "lin"), ("db", 2, "lin")], 1, 0, 1, "PCI-DSS"),
    ("Order Management System",   [("web", 2, "win"), ("app", 3, "win"), ("db", 2, "win")], 1, 1800, 0, "SOX"),
    ("Warehouse Management",      [("app", 4, "lin"), ("db", 2, "lin")], 1, 950, 0, "None"),
    ("Customer Portal",           [("web", 3, "lin"), ("app", 3, "lin"), ("db", 2, "lin")], 2, 84000, 1, "GDPR"),
    ("CRM (Dynamics)",            [("web", 2, "win"), ("app", 3, "win"), ("db", 2, "win")], 2, 1200, 0, "GDPR"),
    ("ERP (SAP ECC)",             [("app", 5, "lin"), ("db", 3, "lin")], 1, 2400, 0, "SOX"),
    ("Business Intelligence",     [("app", 3, "win"), ("db", 2, "win")], 2, 600, 0, "SOX"),
    ("Data Lake Ingest",          [("app", 4, "lin"), ("db", 2, "lin")], 3, 40, 0, "None"),
    ("HR Self-Service",           [("web", 2, "win"), ("app", 2, "win"), ("db", 1, "win")], 2, 5200, 1, "HIPAA"),
    ("Payroll",                   [("app", 2, "win"), ("db", 2, "win")], 1, 120, 0, "SOX"),
    ("Corporate Website (CMS)",   [("web", 3, "lin"), ("db", 1, "lin")], 3, 300000, 1, "None"),
    ("Email Security Gateway",    [("app", 3, "lin")], 2, 0, 1, "None"),
    ("Identity Provider (ADFS)",  [("app", 3, "win")], 1, 0, 1, "None"),
    ("VPN / Remote Access",       [("app", 2, "lin")], 1, 4500, 1, "None"),
    ("Document Management",       [("web", 2, "win"), ("app", 2, "win"), ("db", 2, "win")], 3, 3800, 0, "GDPR"),
    ("Contact Centre Platform",   [("web", 2, "lin"), ("app", 4, "lin"), ("db", 2, "lin")], 1, 900, 0, "PCI-DSS"),
    ("Marketing Automation",      [("app", 3, "lin"), ("db", 1, "lin")], 3, 220, 1, "GDPR"),
    ("Inventory Forecasting",     [("app", 3, "lin"), ("db", 1, "lin")], 3, 60, 0, "None"),
    ("Fraud Detection",           [("app", 4, "lin"), ("db", 2, "lin")], 1, 0, 0, "PCI-DSS"),
    ("Partner API Platform",      [("web", 2, "lin"), ("app", 3, "lin"), ("db", 1, "lin")], 2, 0, 1, "None"),
    ("Legacy Billing (Mainframe offload)", [("app", 2, "win"), ("db", 2, "win")], 2, 80, 0, "SOX"),
    ("Field Service Mobile Backend", [("app", 3, "lin"), ("db", 1, "lin")], 2, 1700, 1, "None"),
    ("Procurement Portal",        [("web", 1, "win"), ("app", 2, "win"), ("db", 1, "win")], 3, 640, 0, "SOX"),
    ("Learning Management",       [("web", 2, "lin"), ("app", 2, "lin"), ("db", 1, "lin")], 4, 9000, 1, "None"),
    ("Facilities / IoT Gateway",  [("app", 2, "lin"), ("db", 1, "lin")], 4, 30, 0, "None"),
    ("Treasury Management",       [("app", 2, "win"), ("db", 1, "win")], 1, 45, 0, "SOX"),
    ("Analytics Sandbox",         [("app", 3, "lin")], 4, 25, 0, "None"),
    ("Print & Output Management", [("app", 2, "win")], 4, 500, 0, "None"),
    ("API Gateway (Kong)",        [("app", 3, "lin")], 1, 0, 1, "None"),
]

INFRA_ROLES = [  # shared services, not tied to a business app
    ("Active Directory Domain Controller", "win", 6),
    ("DNS / DHCP", "lin", 4),
    ("File Server", "win", 5),
    ("Backup (Veeam)", "win", 4),
    ("Monitoring (Zabbix/Grafana)", "lin", 3),
    ("Log Aggregation (ELK)", "lin", 4),
    ("Patch Management (WSUS)", "win", 2),
    ("Jump Host / Bastion", "lin", 3),
    ("Certificate Authority", "win", 2),
    ("Container Registry (Harbor)", "lin", 2),
]


def wchoice(items, weights):
    return random.choices(items, weights=weights, k=1)[0]


# ----------------------------------------------------------------------------
# build servers + applications
# ----------------------------------------------------------------------------
servers = []
apps = []
srv_seq = 0


def new_server(role_hint, os_kind, env_hint=None, app_id=None):
    global srv_seq
    srv_seq += 1
    sid = f"srv-{srv_seq:04d}"

    if os_kind == "win":
        os_name, os_ver, eol, _ = wchoice(WINDOWS_OS, [w for *_, w in WINDOWS_OS])
    else:
        os_name, os_ver, eol, _ = wchoice(LINUX_OS, [w for *_, w in LINUX_OS])

    env = env_hint or wchoice(ENVS, ENV_WEIGHT)
    dc = wchoice(DATACENTERS, DC_WEIGHT)
    if env == "dr":
        dc = "DC-DR-RENO"
    elif dc == "DC-DR-RENO":
        dc = "DC-ASHBURN"
    tag = {"prod": "PRD", "nonprod": "NPD", "dev": "DEV", "dr": "DR"}[env]
    pool = [c for c in CLUSTERS[dc] if tag in c] or \
           [c for c in CLUSTERS[dc] if "NPD" in c] or CLUSTERS[dc]
    cluster = random.choice(pool)

    vcpu, ram = wchoice(SIZES, SIZE_WEIGHT)
    # db tiers skew larger
    if role_hint == "db":
        vcpu = min(64, vcpu * 2)
        ram = min(512, ram * 2)

    prov_disk = random.choice([80, 100, 128, 200, 256, 400, 512, 800, 1024, 2048])
    if role_hint == "db":
        prov_disk = max(prov_disk, random.choice([512, 1024, 2048, 4096]))
    used_disk = round(prov_disk * random.uniform(0.28, 0.86), 1)

    # ~30% have no utilisation data (drives low-confidence right-sizing)
    if random.random() < 0.30:
        cpu_avg = cpu_peak = ram_avg = ""
    else:
        cpu_avg = round(random.uniform(3, 45), 1)
        cpu_peak = round(min(99, cpu_avg + random.uniform(8, 50)), 1)
        ram_avg = round(random.uniform(25, 85), 1)

    powerstate = "poweredOn" if random.random() < 0.93 else "poweredOff"
    prefix = {"web": "web", "app": "app", "db": "db", "infra": "inf"}.get(role_hint, "srv")
    hostname = f"{prefix}{env[:1]}{srv_seq:04d}".lower()

    notes_bits = ["VMware vSphere 7.0 VM"]
    if os_name == "Windows Server" and os_ver == "2012 R2":
        notes_bits.append("OS past end-of-support - remediation or ESU required")
    if os_name == "Red Hat Enterprise Linux" and os_ver.startswith("7"):
        notes_bits.append("RHEL 7 past maintenance support")
    if powerstate == "poweredOff":
        notes_bits.append("powered off at discovery - confirm if decommissioned")
    if cpu_avg == "" :
        notes_bits.append("no performance history from vCenter (< 30 days)")

    servers.append({
        "server_id": sid, "hostname": hostname, "env": env,
        "os_name": os_name, "os_version": os_ver, "os_eol_date": eol,
        "vcpu": vcpu, "ram_gb": ram,
        "provisioned_disk_gb": prov_disk, "used_disk_gb": used_disk,
        "cpu_avg_pct": cpu_avg, "cpu_peak_pct": cpu_peak, "cpu_p95_pct": "",
        "ram_avg_pct": ram_avg, "ram_p95_pct": "",
        # 30-day rollups - filled by build_performance() for monitored servers
        "disk_iops_avg": "", "disk_iops_peak": "",
        "net_in_gb_30d": "", "net_out_gb_30d": "",
        "cluster": cluster, "datacenter": dc, "powerstate": powerstate,
        "app_id": app_id or "", "notes": "; ".join(notes_bits),
        "_role": role_hint,   # scratch, dropped before write
    })
    return sid


WIN_TARGET, LIN_TARGET = 150, 100
win_count = lin_count = 0


def os_for(kind):
    """Resolve 'any'/'win'/'lin' to a concrete kind, respecting the 150/100 split."""
    global win_count, lin_count
    if kind == "win" and win_count < WIN_TARGET + 25:
        win_count += 1
        return "win"
    if kind == "lin" and lin_count < LIN_TARGET + 25:
        lin_count += 1
        return "lin"
    # fall back to whichever is under target
    if win_count / WIN_TARGET <= lin_count / LIN_TARGET:
        win_count += 1
        return "win"
    lin_count += 1
    return "lin"


app_seq = 0
for (name, tiers, crit, users, inet, comp) in APP_DEFS:
    app_seq += 1
    aid = f"app-{app_seq:02d}"
    env_hint = "prod" if crit <= 2 else wchoice(["prod", "nonprod"], [0.7, 0.3])
    db_engine = ""
    stacks = []
    for (role, count, okind) in tiers:
        for _ in range(count):
            k = os_for("win" if okind == "win" else "lin" if okind == "lin" else "any")
            sid = new_server(role, k, env_hint, aid)
            pool = WIN_STACKS if k == "win" else LINUX_STACKS
            if role == "db":
                cand = [s for s in pool if s[1]]
                st, eng = random.choice(cand or pool)
                db_engine = eng or db_engine
            else:
                st, _ = random.choice([s for s in pool if not s[1]] or pool)
            stacks.append(st)
    tech_stack = "; ".join(sorted(set(stacks)))[:500]
    apps.append({
        "app_id": aid, "app_name": name,
        "business_owner": random.choice(OWNERS),
        "criticality": crit, "users": users if users else "",
        "tech_stack": tech_stack, "db_engine": db_engine,
        "internet_facing": inet, "compliance_scope": comp,
        "disposition": "", "complexity": "", "wave": "",
    })

# infra app bucket
app_seq += 1
infra_aid = f"app-{app_seq:02d}"
apps.append({
    "app_id": infra_aid, "app_name": "Core IT Infrastructure Services",
    "business_owner": "L. Andersson (Corporate IT)", "criticality": 1, "users": "",
    "tech_stack": "Active Directory; DNS/DHCP; Veeam; ELK; Zabbix; WSUS; PKI",
    "db_engine": "", "internet_facing": 0, "compliance_scope": "None",
    "disposition": "", "complexity": "", "wave": "",
})
for (rname, okind, count) in INFRA_ROLES:
    for _ in range(count):
        new_server("infra", os_for(okind), wchoice(["prod", "dr"], [0.85, 0.15]), infra_aid)

# top up to exactly 250 with standalone / unassigned utility VMs
STANDALONE_NOTES = "standalone utility VM - owner unconfirmed"
while len(servers) < 250:
    k = os_for("any")
    sid = new_server("srv", k, wchoice(["nonprod", "dev", "prod"], [0.4, 0.4, 0.2]), "")
    servers[-1]["notes"] = servers[-1]["notes"] + "; " + STANDALONE_NOTES

# trim if a tier pushed us over 250
servers = servers[:250]
srv_ids = {s["server_id"] for s in servers}


def _reos(s, kind):
    """Reassign a server's OS to the other family and fix the OS-derived note bits."""
    table = WINDOWS_OS if kind == "win" else LINUX_OS
    name, ver, eol, _ = wchoice(table, [w for *_, w in table])
    s["os_name"], s["os_version"], s["os_eol_date"] = name, ver, eol
    bits = [b for b in s["notes"].split("; ")
            if "end-of-support" not in b and "maintenance support" not in b]
    if name == "Windows Server" and ver == "2012 R2":
        bits.insert(1, "OS past end-of-support - remediation or ESU required")
    if name == "Red Hat Enterprise Linux" and ver.startswith("7"):
        bits.insert(1, "RHEL 7 past maintenance support")
    s["notes"] = "; ".join(bits)


# force the split to exactly 150 Windows / 100 Linux, flipping the least-attached
# servers first (standalone, then infra, then web tiers - never db/app tiers)
def _flip_rank(s):
    if not s["app_id"]:
        return 0
    if s["hostname"].startswith("inf"):
        return 1
    if s["hostname"].startswith("web"):
        return 2
    return 3


TARGET_WIN = 150
win_now = [s for s in servers if s["os_name"] == "Windows Server"]
lin_now = [s for s in servers if s["os_name"] != "Windows Server"]
if len(win_now) < TARGET_WIN:
    for s in sorted(lin_now, key=lambda s: (_flip_rank(s), s["server_id"]))[:TARGET_WIN - len(win_now)]:
        _reos(s, "win")
elif len(win_now) > TARGET_WIN:
    for s in sorted(win_now, key=lambda s: (_flip_rank(s), s["server_id"]))[:len(win_now) - TARGET_WIN]:
        _reos(s, "lin")

win_n = sum(1 for s in servers if s["os_name"] == "Windows Server")
lin_n = len(servers) - win_n
print(f"servers: {len(servers)}  (Windows {win_n}, Linux {lin_n})")
print(f"applications: {len(apps)}")

# ----------------------------------------------------------------------------
# performance - 30 daily samples per MONITORED server (those that already have a
# summary reading). Newly-provisioned / unmonitored VMs stay blank so the
# low-confidence right-sizing path is still exercised.
#   CPU %, memory %, disk IOPS, and network ingress/egress (GB/day + peak Mbps).
# servers.csv gets the rollups; performance.csv gets the daily series.
# ----------------------------------------------------------------------------
from datetime import timedelta

WINDOW_DAYS = 30
WINDOW_END = date(2026, 9, 6)                       # matches the repo "today"
WINDOW_START = WINDOW_END - timedelta(days=WINDOW_DAYS - 1)

# per-role shape: IOPS per (2 vCPU), daily network GB base (in/out), spike size
ROLE_PROFILE = {
    "web":   dict(iops_base=40,  net_in=2.0, net_out=8.0, burst=2.3),
    "app":   dict(iops_base=85,  net_in=4.0, net_out=3.0, burst=2.0),
    "db":    dict(iops_base=380, net_in=2.5, net_out=1.8, burst=1.7),
    "infra": dict(iops_base=55,  net_in=1.0, net_out=1.0, burst=1.6),
    "srv":   dict(iops_base=35,  net_in=0.6, net_out=0.6, burst=1.8),
}

perf_rows = []
app_by_id = {a["app_id"]: a for a in apps}


def build_performance():
    for s in servers:
        if s["cpu_avg_pct"] == "" or s["powerstate"] == "poweredOff":
            continue
        rng = random.Random(f"perf::{s['server_id']}")   # deterministic per server
        prof = ROLE_PROFILE.get(s["_role"], ROLE_PROFILE["srv"])
        vcpu = float(s["vcpu"])
        app = app_by_id.get(s["app_id"])
        users = float(app["users"]) if app and app["users"] not in ("", None) else 50.0
        inet = bool(app and app["internet_facing"] == 1)
        user_scale = 1 + users / 60000.0                 # gentle: 210k users -> ~4.5x

        cpu_center = float(s["cpu_avg_pct"])
        mem_center = float(s["ram_avg_pct"]) if s["ram_avg_pct"] != "" else rng.uniform(35, 75)
        iops_center = prof["iops_base"] * max(1.0, vcpu / 2) * rng.uniform(0.6, 1.4)
        net_out_day = prof["net_out"] * user_scale * (1.8 if inet else 1.0) * rng.uniform(0.7, 1.4)
        net_in_day = prof["net_in"] * (1 + users / 120000.0) * rng.uniform(0.7, 1.4)

        cpu_avgs, cpu_peaks, mem_avgs, iops_avgs, iops_peaks = [], [], [], [], []
        nin_sum = nout_sum = 0.0

        for d in range(WINDOW_DAYS):
            day = WINDOW_START + timedelta(days=d)
            weekend = day.weekday() >= 5
            f = (0.65 if weekend else 1.0) * rng.uniform(0.85, 1.15)
            spike = prof["burst"] if rng.random() < 0.06 else 1.0

            cpu_a = min(94, max(1, cpu_center * f * rng.uniform(0.85, 1.12)))
            cpu_pk = min(99, cpu_a * rng.uniform(1.25, 1.7) * (spike if spike > 1 else 1.0))
            cpu_p95 = min(99, cpu_a + (cpu_pk - cpu_a) * 0.65)
            mem_a = min(95, max(6, mem_center * (0.92 + 0.16 * f)))
            mem_pk = min(99, mem_a * rng.uniform(1.05, 1.22))
            mem_p95 = min(99, mem_a + (mem_pk - mem_a) * 0.65)

            io_a = iops_center * f * rng.uniform(0.75, 1.25)
            io_pk = io_a * rng.uniform(1.8, 2.8) * (spike if spike > 1 else 1.0)
            io_rd = io_a * (0.7 if s["_role"] == "db" else 0.55)
            io_wr = io_a - io_rd
            io_mbps = io_a * (0.03 if s["_role"] == "db" else 0.05)

            nin = max(0.02, net_in_day * f * rng.uniform(0.65, 1.4) * (spike if spike > 1 else 1.0))
            nout = max(0.02, net_out_day * f * rng.uniform(0.65, 1.45) * (spike if spike > 1 else 1.0))
            nin_mbps = nin * 8000 / 86400 * rng.uniform(4, 10)         # peak burst >> daily mean
            nout_mbps = nout * 8000 / 86400 * rng.uniform(4, 11)

            cpu_avgs.append(cpu_a); cpu_peaks.append(cpu_pk)
            mem_avgs.append(mem_a); iops_avgs.append(io_a); iops_peaks.append(io_pk)
            nin_sum += nin; nout_sum += nout

            perf_rows.append({
                "server_id": s["server_id"], "sample_date": day.isoformat(),
                "cpu_avg_pct": round(cpu_a, 1), "cpu_peak_pct": round(cpu_pk, 1),
                "cpu_p95_pct": round(cpu_p95, 1),
                "mem_avg_pct": round(mem_a, 1), "mem_peak_pct": round(mem_pk, 1),
                "mem_p95_pct": round(mem_p95, 1),
                "disk_iops_avg": round(io_a, 1), "disk_iops_peak": round(io_pk, 1),
                "disk_read_iops_avg": round(io_rd, 1), "disk_write_iops_avg": round(io_wr, 1),
                "disk_throughput_mbps_avg": round(io_mbps, 2),
                "net_in_gb": round(nin, 3), "net_out_gb": round(nout, 3),
                "net_in_peak_mbps": round(nin_mbps, 1), "net_out_peak_mbps": round(nout_mbps, 1),
            })

        # roll up into servers.csv (keep it the single source for summary figures).
        # p95 = 95th percentile of the daily averages -> the "sustained busy" signal
        # right-sizing should use (not the absolute 30-day peak).
        def _p95(xs):
            xs = sorted(xs)
            return xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))]

        s["cpu_avg_pct"] = round(sum(cpu_avgs) / len(cpu_avgs), 1)
        s["cpu_peak_pct"] = round(max(cpu_peaks), 1)
        s["cpu_p95_pct"] = round(_p95(cpu_avgs), 1)
        s["ram_avg_pct"] = round(sum(mem_avgs) / len(mem_avgs), 1)
        s["ram_p95_pct"] = round(_p95(mem_avgs), 1)
        s["disk_iops_avg"] = round(sum(iops_avgs) / len(iops_avgs), 1)
        s["disk_iops_peak"] = round(max(iops_peaks), 1)
        s["net_in_gb_30d"] = round(nin_sum, 1)
        s["net_out_gb_30d"] = round(nout_sum, 1)


build_performance()
_monitored = sum(1 for s in servers if s["cpu_avg_pct"] != "")
print(f"performance: {len(perf_rows)} daily samples over {WINDOW_DAYS} days "
      f"({_monitored}/{len(servers)} servers monitored)")

# ----------------------------------------------------------------------------
# dependencies - edges plus 30-day OBSERVED flow metrics (bytes moved, connection
# count, last-seen). ~4% of edges are stale (last seen weeks ago) to exercise the
# "is this dependency still real?" question in an assessment.
# ----------------------------------------------------------------------------
deps = []
by_app_role = {}
for s in servers:
    if not s["app_id"]:
        continue
    role = s["hostname"][:3]
    by_app_role.setdefault((s["app_id"], role), []).append(s["server_id"])

PORTS = {
    "web->app": [(8080, "HTTP"), (8443, "HTTPS"), (443, "HTTPS")],
    "app->db": [(1433, "TDS"), (1521, "TNS"), (5432, "PGSQL"), (3306, "MYSQL"), (27017, "MONGO")],
    "user->web": [(443, "HTTPS")],
}
CONF = ["high", "high", "medium", "low"]
# kind -> (GB over 30d lo, hi), (connections over 30d lo, hi)
FLOW = {
    "web->app":   ((40, 900),      (80_000, 3_000_000)),
    "app->db":    ((15, 450),      (400_000, 22_000_000)),
    "ldap":       ((0.8, 18),      (4_000, 90_000)),
    "dns":        ((0.15, 3.5),    (18_000, 420_000)),
    "internet":   ((300, 5200),    (60_000, 2_400_000)),
}


def add_dep(src, dst, port, proto, direction, conf, kind):
    (glo, ghi), (clo, chi) = FLOW[kind]
    gb = round(random.uniform(glo, ghi) * random.uniform(0.6, 1.5), 2)
    flows = int(random.uniform(clo, chi))
    if random.random() < 0.04:                      # stale edge
        seen = WINDOW_START - timedelta(days=random.randint(3, 25))
        gb = round(gb * random.uniform(0.01, 0.15), 2)
        flows = int(flows * random.uniform(0.01, 0.1))
        conf = "low"
    else:
        seen = WINDOW_END - timedelta(days=random.randint(0, 2))
    deps.append({
        "src_id": src, "dst_id": dst, "port": port, "protocol": proto,
        "direction": direction, "confidence": conf,
        "bytes_30d_gb": gb, "flows_30d": flows, "last_seen": seen.isoformat(),
    })


for app in apps:
    aid = app["app_id"]
    webs = by_app_role.get((aid, "web"), [])
    apps_ = by_app_role.get((aid, "app"), [])
    dbs = by_app_role.get((aid, "db"), [])
    for w in webs:
        for a in apps_:
            p, pr = random.choice(PORTS["web->app"])
            add_dep(w, a, p, pr, "outbound", random.choice(CONF), "web->app")
    src_tier = apps_ or webs
    for a in src_tier:
        for d in dbs:
            p, pr = random.choice(PORTS["app->db"])
            add_dep(a, d, p, pr, "outbound", random.choice(CONF), "app->db")

# every server talks to AD + DNS + monitoring
dc_ids = [s["server_id"] for s in servers if s["hostname"].startswith("inf") and s["os_name"] == "Windows Server"][:6]
dns_ids = [s["server_id"] for s in servers if s["hostname"].startswith("inf") and s["os_name"] != "Windows Server"][:4]
for s in servers:
    if s["powerstate"] == "poweredOff":
        continue
    if dc_ids and random.random() < 0.9:
        add_dep(s["server_id"], random.choice(dc_ids), random.choice([389, 636, 88]), "LDAP", "outbound", "medium", "ldap")
    if dns_ids and random.random() < 0.8:
        add_dep(s["server_id"], random.choice(dns_ids), 53, "DNS", "outbound", "low", "dns")

# internet-facing apps get an inbound edge from "internet"
for app in apps:
    if app["internet_facing"] == 1:
        for w in by_app_role.get((app["app_id"], "web"), []) or by_app_role.get((app["app_id"], "app"), [])[:1]:
            add_dep("internet", w, 443, "HTTPS", "inbound", "high", "internet")

print(f"dependencies: {len(deps)}")

# ----------------------------------------------------------------------------
# storage
# ----------------------------------------------------------------------------
storage = []
st_seq = 0
TARGETS_BLOCK = ["Premium SSD v2", "Premium SSD P20", "Premium SSD P30", "Standard SSD E20", "Ultra Disk"]
for s in servers:
    st_seq += 1
    # OS disk
    storage.append({
        "storage_id": f"stg-{st_seq:04d}", "server_id": s["server_id"], "type": "block",
        "size_gb": 128 if s["os_name"] == "Windows Server" else 64,
        "iops": random.choice([500, 1100, 2300]),
        "target_service": "Premium SSD P10",
    })
    # data disk(s)
    is_db = s["hostname"].startswith("db")
    n_data = random.choice([1, 1, 2, 3]) if is_db else random.choice([0, 1, 1, 2])
    remaining = float(s["provisioned_disk_gb"])
    for _ in range(n_data):
        st_seq += 1
        chunk = round(remaining / max(1, n_data) * random.uniform(0.6, 1.1), 1)
        storage.append({
            "storage_id": f"stg-{st_seq:04d}", "server_id": s["server_id"], "type": "block",
            "size_gb": max(32, chunk),
            "iops": random.choice([2300, 5000, 7500, 16000]) if is_db else random.choice([500, 1100, 2300, 5000]),
            "target_service": random.choice(TARGETS_BLOCK),
        })
    if is_db:
        st_seq += 1
        storage.append({
            "storage_id": f"stg-{st_seq:04d}", "server_id": s["server_id"], "type": "db",
            "size_gb": round(float(s["provisioned_disk_gb"]) * random.uniform(0.4, 0.9), 1),
            "iops": random.choice([5000, 12000, 20000]),
            "target_service": random.choice(["SQL Managed Instance", "Azure SQL DB Hyperscale",
                                             "PostgreSQL Flexible Server", "Oracle DB@Azure"]),
        })

# a handful of shared file shares (no single server owner -> attach to a file server)
file_servers = [s["server_id"] for s in servers if "File Server" in s.get("notes", "") or s["hostname"].startswith("inf")][:5]
for i, fs in enumerate(file_servers):
    st_seq += 1
    storage.append({
        "storage_id": f"stg-{st_seq:04d}", "server_id": fs, "type": "file",
        "size_gb": random.choice([2048, 4096, 8192, 16384]),
        "iops": random.choice([3000, 5000]),
        "target_service": random.choice(["Azure Files Premium", "Azure NetApp Files"]),
    })

print(f"storage volumes: {len(storage)}")

# ----------------------------------------------------------------------------
# write CSVs
# ----------------------------------------------------------------------------
def write_csv(name, rows, cols):
    path = os.path.join(HERE, name)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"  wrote {name}  ({len(rows)} rows)")


for s in servers:
    s.pop("_role", None)

write_csv("servers.csv", servers, [
    "server_id", "hostname", "env", "os_name", "os_version", "os_eol_date", "vcpu",
    "ram_gb", "provisioned_disk_gb", "used_disk_gb", "cpu_avg_pct", "cpu_peak_pct",
    "cpu_p95_pct", "ram_avg_pct", "ram_p95_pct", "disk_iops_avg", "disk_iops_peak",
    "net_in_gb_30d", "net_out_gb_30d",
    "cluster", "datacenter", "powerstate", "app_id", "notes",
])
write_csv("applications.csv", apps, [
    "app_id", "app_name", "business_owner", "criticality", "users", "tech_stack",
    "db_engine", "internet_facing", "compliance_scope", "disposition", "complexity", "wave",
])
write_csv("dependencies.csv", deps, [
    "src_id", "dst_id", "port", "protocol", "direction", "confidence",
    "bytes_30d_gb", "flows_30d", "last_seen",
])
write_csv("storage.csv", storage,
          ["storage_id", "server_id", "type", "size_gb", "iops", "target_service"])
write_csv("performance.csv", perf_rows, [
    "server_id", "sample_date", "cpu_avg_pct", "cpu_peak_pct", "cpu_p95_pct",
    "mem_avg_pct", "mem_peak_pct", "mem_p95_pct",
    "disk_iops_avg", "disk_iops_peak", "disk_read_iops_avg", "disk_write_iops_avg",
    "disk_throughput_mbps_avg", "net_in_gb", "net_out_gb",
    "net_in_peak_mbps", "net_out_peak_mbps",
])

print(f"\nGenerated {date.today()} - seed 42. Load with sample-estate/load_estate.py")
