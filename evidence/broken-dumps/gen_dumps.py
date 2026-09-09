"""
Generate the E10.2 broken-dump corpus — deterministic, committed alongside its
output in `dumps/`. Each file is a different way a client inventory export can be
damaged; `check.py` runs the ingestion pipeline over every one and asserts it is
handled per E1.4 (unrecognised / rejected / degraded-but-named — never a silent
partial load).

    python evidence/broken-dumps/gen_dumps.py
"""
from __future__ import annotations

import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dumps")

_SERVER_HEADER = ("server_id,hostname,env,os_name,os_version,os_eol_date,vcpu,ram_gb,"
                  "provisioned_disk_gb,used_disk_gb,cpu_avg_pct,cpu_peak_pct,cpu_p95_pct,"
                  "ram_avg_pct,ram_p95_pct,cluster,datacenter,powerstate,app_id,notes")


def _good_row(i: int) -> str:
    return (f"srv-{i:04d},host{i:04d},prod,Windows Server,2019,2029-01-09,4,16,"
            f"200,90,12.0,34.0,20.0,55.0,60.0,CL1,DC-1,poweredOn,app-01,")


def write(name: str, data, mode: str = "w", **kw):
    path = os.path.join(OUT, name)
    if mode == "wb":
        with open(path, "wb") as fh:
            fh.write(data)
    else:
        with open(path, "w", encoding=kw.get("encoding", "utf-8"), newline="\n") as fh:
            fh.write(data)
    print(f"  wrote dumps/{name}")


def main() -> None:
    os.makedirs(OUT, exist_ok=True)

    # 1. a file whose headers match no source profile at all
    write("01_unrecognised_firewall_export.csv",
          "rule_id,source_zone,dest_zone,service,port,action,last_hit\n"
          "R-001,DMZ,INTERNAL,https,443,allow,2026-09-01\n"
          "R-002,ANY,DMZ,ssh,22,deny,2026-08-14\n")

    # 2. completely empty file
    write("02_empty.csv", "")

    # 3. a valid servers header with zero data rows
    write("03_servers_header_only.csv", _SERVER_HEADER + "\n")

    # 4. a performance export with the required sample_date column missing
    write("04_performance_no_dates.csv",
          "server_id,cpu_avg_pct,cpu_peak_pct,mem_avg_pct\n"
          + "".join(f"srv-{i:04d},14.2,38.0,55.1\n" for i in range(1, 9)))

    # 5. ragged rows — some short, some long; OS ends up missing on most
    rows = [_SERVER_HEADER]
    for i in range(1, 13):
        if i % 3 == 0:                       # short: stops after ram_gb
            rows.append(f"srv-{i:04d},host{i:04d},prod,,,,4,16")
        elif i % 3 == 1:                     # long: extra trailing fields
            rows.append(_good_row(i) + ",EXTRA,MORE,STILLMORE")
        else:
            rows.append(_good_row(i))
    write("05_servers_ragged_rows.csv", "\n".join(rows) + "\n")

    # 6. garbage in the numeric columns
    rows = [_SERVER_HEADER]
    junk_vcpu = ["N/A", "eight", "-", "TBD", "?", "four"]
    junk_ram = ["16 GB", "unknown", "32GB", "n/a", "sixteen", "—"]
    for i in range(1, 13):
        rows.append(f"srv-{i:04d},host{i:04d},prod,Ubuntu,22.04 LTS,2027-04-30,"
                    f"{junk_vcpu[i % len(junk_vcpu)]},{junk_ram[i % len(junk_ram)]},"
                    f"200,90,,,,,,CL1,DC-1,poweredOn,app-01,")
    write("06_servers_garbage_numerics.csv", "\n".join(rows) + "\n")

    # 7. the same server_id repeated with different specs
    rows = [_SERVER_HEADER, _good_row(1)]
    rows.append("srv-0001,host0001b,prod,Windows Server,2016,2027-01-12,8,32,"
                "400,200,,,,,,CL2,DC-1,poweredOn,app-02,second copy")
    rows.append("srv-0001,host0001c,dr,Windows Server,2016,2027-01-12,2,8,"
                "100,40,,,,,,CL3,DC-2,poweredOff,app-02,third copy")
    rows += [_good_row(i) for i in range(2, 8)]
    write("07_servers_duplicate_ids.csv", "\n".join(rows) + "\n")

    # 8. UTF-16 encoded (BOM + NUL bytes) — headers become unreadable
    text = _SERVER_HEADER + "\n" + "\n".join(_good_row(i) for i in range(1, 6)) + "\n"
    write("08_servers_utf16.csv", text.encode("utf-16"), mode="wb")

    # 9. dependencies that point at servers not present in any uploaded file
    rows = ["src_id,dst_id,port,protocol,direction,confidence,bytes_30d_gb,flows_30d,last_seen"]
    for i in range(1, 9):
        rows.append(f"srv-9{i:03d},srv-8{i:03d},1433,TDS,outbound,high,120,500000,2026-09-05")
    write("09_dependencies_orphan_endpoints.csv", "\n".join(rows) + "\n")

    print(f"\n{len(os.listdir(OUT))} dumps in {OUT}")


if __name__ == "__main__":
    main()
