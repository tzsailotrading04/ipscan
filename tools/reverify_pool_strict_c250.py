"""
reverify_pool_strict_c250.py
Resumes re-verification of the pool with CONCURRENCY = 250 to completion:
- Starts from index 239,900 to 273,988 (remaining 34,088 proxies)
- Preserves all 3,342 already verified survivors in ip/harvest/real_pool.txt
- Appends new survivors
- Reports final unique count in real_pool.txt and pass rate per ASN class
- Leaves backup pool untouched
"""
import asyncio
import bisect
import json
import os
import socket
import ssl
import struct
import sys
import time
from collections import Counter

ROOT = r"D:\DEpinFarm"
POOL_BACKUP = os.path.join(ROOT, "ip", "harvest", "backup_pool_20261028_182133.txt")
OUT_REAL_POOL = os.path.join(ROOT, "ip", "harvest", "real_pool.txt")
ASN_FILE = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")
PROGRESS_FILE = os.path.join(ROOT, "ip", "harvest", "reverify_progress.json")
SUMMARY_FILE = os.path.join(ROOT, "ip", "harvest", "final_reverify_summary.json")

CONCURRENCY = 250
TIMEOUT_CONNECT = 5.0
TIMEOUT_STAGE = 5.0

TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
CLIENT_HELLOS = {}
for _t in TARGETS:
    _ctx = ssl.create_default_context()
    _bio_in, _bio_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    _sslobj = _ctx.wrap_bio(_bio_in, _bio_out, server_hostname=_t)
    try:
        _sslobj.do_handshake()
    except ssl.SSLWantReadError:
        pass
    CLIENT_HELLOS[_t] = _bio_out.read()

# ASN Classifier keywords
DC_SUBS = (
    "hetzner", "ovh", "digitalocean", "linode", "vultr", "contabo", "scaleway", "leaseweb",
    "colocrossing", "psychz", "frantech", "hosthatch", "racknerd", "servermania", "amazon",
    "aws", "google", "gcp", "microsoft", "azure", "oracle", "alibaba", "tencent", "huawei",
    "m247", "choopa", "melbicom", "netcup", "quadranet", "gcore", "zenlayer", "upcloud",
    "hivelocity", "worldstream", "hostens", "serverius", "server", "servers", "vps",
    "dedicated", "colo", "colocation", "hosting", "host", "hostinger", "cloud", "datacenter",
    "data center", "akamai", "fastly", "cloudflare", "ramnode", "performive", "datawagon",
    "dmit", "colohouse", "hostdime", "liquidweb", "ipxo", "tierpoint", "cogent", "shinjiru",
    "fdcservers", "intergrid", "tzulo", "shock", "quadrix", "hostkey", "blazingfast",
    "time4vps", "timeweb", "ionos", "godaddy", "rackspace", "equinix", "cdn", "freakhosting",
    "ucloud", "ctrls", "aeza", "zscaler", "gtt-backbone", "tor-exit", "emerald-onion",
    "raksmart", "ponynet"
)

MOB_SUBS = (
    "mobile", "cellular", "wireless", "gsm", "lte", "4g", "5g", "cellco", "t-mobile",
    "turkcell", "jio", "reliance", "claro", "movistar", "vodafone", "airtel", "smartfren",
    "telkomsel", "indosat", "zain", "etisalat", "safaricom", "mtn", "ooredoo"
)

ISP_SUBS = (
    "telecom", "telekom", "telephon", "telecomunicacoes", "telecomunicaciones", "broadband",
    "cable", "communication", "comunicaciones", "comunicacion", "jaringan", "internet",
    "fiber", "fibre", "fibra", "dsl", "adsl", "isp", "wireless", "telefonica", "telia", "telenor", "kpn",
    "swisscom", "comcast", "verizon", "charter", "cox", "centurylink", "frontier",
    "windstream", "mediacom", "altice", "rogers", "bell canada", "telus", "shaw",
    "videotron", "at&t", "bellsouth", "telkom", "telstra", "optus", "iinet", "tpg",
    "vocus", "singtel", "starhub", "pccw", "hkt", "china telecom", "china unicom",
    "chinanet", "kddi", "softbank", "biglobe", "plala", "so-net", "jcom", "viettel",
    "vnpt", "fpt", "pln", "ufinet", "cantv", "myrepublic", "tot-net",
    "idnic", "redes", "kabel", "satelit", "starlink"
)

def ip_to_u32(ip):
    return struct.unpack("!I", socket.inet_aton(ip))[0]

def load_asn_table():
    print(f"Loading ASN table from {ASN_FILE}...")
    t0 = time.time()
    rows = []
    with open(ASN_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 5:
                try:
                    rows.append((int(parts[0]), int(parts[1]), parts[2], parts[3], parts[4]))
                except ValueError:
                    pass
    rows.sort()
    starts = [r[0] for r in rows]
    print(f"Loaded {len(rows):,} ASN ranges in {time.time()-t0:.2f}s")
    return rows, starts

asn_rows, asn_starts = load_asn_table()

def classify_ip(ip_str):
    try:
        u = ip_to_u32(ip_str)
    except Exception:
        return "UNKNOWN", "0", "UNKNOWN"
    i = bisect.bisect_right(asn_starts, u) - 1
    if i >= 0 and asn_rows[i][0] <= u <= asn_rows[i][1]:
        asn, org = asn_rows[i][2], asn_rows[i][4]
        org_l = org.lower()
        if any(m in org_l for m in MOB_SUBS):
            return "MOBILE", asn, org
        if any(d in org_l for d in DC_SUBS):
            return "DATACENTER", asn, org
        if any(isp in org_l for isp in ISP_SUBS):
            return "RESIDENTIAL", asn, org
        return "UNKNOWN", asn, org
    return "UNKNOWN", "0", "UNKNOWN"

async def inline_probe_connected(s, target, timeout=5.0):
    try:
        loop = asyncio.get_running_loop()
        req = f"CONNECT {target}:443 HTTP/1.1\\r\\nHost: {target}:443\\r\\n\\r\\n".encode()
        await loop.sock_sendall(s, req)
        resp = b""
        t_end = time.monotonic() + timeout
        while b"\\r\\n\\r\\n" not in resp:
            if time.monotonic() > t_end:
                return False
            c = await asyncio.wait_for(loop.sock_recv(s, 512), timeout=timeout)
            if not c:
                return False
            resp += c
        first_line = resp.split(b"\\r\\n")[0]
        if not (resp.startswith(b"HTTP/") and (b" 200" in first_line or b" 2" in first_line)):
            return False
        parts = resp.split(b"\\r\\n\\r\\n", 1)
        trailing = parts[1] if len(parts) > 1 else b""
        if trailing:
            return trailing[:1] == b"\\x16"
        await loop.sock_sendall(s, CLIENT_HELLOS[target])
        b1 = await asyncio.wait_for(loop.sock_recv(s, 1), timeout=timeout)
        return b1 == b"\\x16"
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass

async def probe_single_target(ip, port, target, timeout=5.0):
    loop = asyncio.get_running_loop()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setblocking(False)
    try:
        await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=timeout)
        return await inline_probe_connected(s, target, timeout=timeout)
    except Exception:
        try:
            s.close()
        except Exception:
            pass
        return False

async def verify_proxy(ip, port):
    loop = asyncio.get_running_loop()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setblocking(False)
    try:
        await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=TIMEOUT_CONNECT)
    except Exception:
        try:
            s.close()
        except Exception:
            pass
        return False, None

    if await inline_probe_connected(s, "speed.cloudflare.com", timeout=TIMEOUT_STAGE):
        return True, "speed.cloudflare.com"

    for t in ["www.google.com", "one.one.one.one"]:
        if await probe_single_target(ip, port, t, timeout=TIMEOUT_STAGE):
            return True, t

    return False, None

async def worker(queue, sem, out_fp, stats, total_count, lock, existing_passed_set):
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            break

        addr, full_line, asn_class, asn, org = item
        ip, port_str = addr.split(":")
        port = int(port_str)

        async with sem:
            passed, winning_target = await verify_proxy(ip, port)

        async with lock:
            stats["tested"] += 1
            stats["by_class"][asn_class]["tested"] += 1
            if passed:
                stats["passed"] += 1
                stats["by_class"][asn_class]["passed"] += 1
                if addr not in existing_passed_set:
                    existing_passed_set.add(addr)
                    out_fp.write(f"{addr}\t{winning_target}\t{asn_class}\t{asn}\t{org}\n")
                    out_fp.flush()

            tested = stats["tested"]
            if tested % 500 == 0 or tested == total_count:
                dt = max(0.1, time.time() - stats["start_time"])
                speed = tested / dt
                pass_rate = (stats["passed"] / max(1, tested)) * 100
                print(f"[{tested:,}/{total_count:,} ({tested/total_count*100:5.1f}%)] "
                      f"Total Passed={stats['passed']:,} ({pass_rate:4.2f}%) | "
                      f"DC={stats['by_class']['DATACENTER']['passed']}/{stats['by_class']['DATACENTER']['tested']} | "
                      f"RES={stats['by_class']['RESIDENTIAL']['passed']}/{stats['by_class']['RESIDENTIAL']['tested']} | "
                      f"MOB={stats['by_class']['MOBILE']['passed']}/{stats['by_class']['MOBILE']['tested']} | "
                      f"{speed:.1f}/s", flush=True)

        queue.task_done()

async def main():
    print("=" * 80)
    print("STRICT MULTI-TARGET RE-VERIFICATION (CONCURRENCY = 250) TO COMPLETION")
    print(f"Source Backup: {POOL_BACKUP} (READ-ONLY, UNTOUCHED)")
    print(f"Destination:   {OUT_REAL_POOL}")
    print(f"Concurrency:   {CONCURRENCY}")
    print(f"Targets:       {', '.join(TARGETS)}")
    print("=" * 80)

    # 1. Load all proxies from backup file
    items = []
    seen_addrs = set()
    with open(POOL_BACKUP, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            addr = line.split("\t")[0].split()[0]
            if ":" in addr and addr not in seen_addrs:
                seen_addrs.add(addr)
                ip = addr.split(":")[0]
                cls, asn, org = classify_ip(ip)
                items.append((addr, line, cls, asn, org))

    total_pool_size = len(items)
    print(f"Loaded {total_pool_size:,} unique proxies from master backup.")

    # 2. Read already passed survivors from OUT_REAL_POOL
    existing_passed_set = set()
    existing_by_class_passed = Counter()
    if os.path.exists(OUT_REAL_POOL):
        with open(OUT_REAL_POOL, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.strip().split("\t")
                if parts and ":" in parts[0]:
                    addr = parts[0].strip()
                    existing_passed_set.add(addr)
                    cls = parts[2].strip() if len(parts) >= 3 else "UNKNOWN"
                    existing_by_class_passed[cls] += 1

    print(f"Already verified in real_pool.txt: {len(existing_passed_set):,} survivors ({dict(existing_by_class_passed)})")

    # 3. Determine start index
    # Find last addr from real_pool.txt in items
    start_idx = 0
    if existing_passed_set:
        # Find maximum index of existing passed addrs
        max_seen_idx = 0
        for i, it in enumerate(items):
            if it[0] in existing_passed_set:
                if i > max_seen_idx:
                    max_seen_idx = i
        # Safe resume point: max_seen_idx + 1
        start_idx = min(total_pool_size, max_seen_idx + 1)

    print(f"Resuming scan from index {start_idx:,} / {total_pool_size:,} ({total_pool_size - start_idx:,} remaining).")

    # Calculate tested counts up to start_idx
    tested_up_to_start = start_idx
    tested_by_class_up_to_start = Counter(items[i][2] for i in range(start_idx))

    stats = {
        "start_time": time.time(),
        "tested": tested_up_to_start,
        "passed": len(existing_passed_set),
        "by_class": {
            "DATACENTER": {"tested": tested_by_class_up_to_start["DATACENTER"], "passed": existing_by_class_passed["DATACENTER"]},
            "RESIDENTIAL": {"tested": tested_by_class_up_to_start["RESIDENTIAL"], "passed": existing_by_class_passed["RESIDENTIAL"]},
            "MOBILE": {"tested": tested_by_class_up_to_start["MOBILE"], "passed": existing_by_class_passed["MOBILE"]},
            "UNKNOWN": {"tested": tested_by_class_up_to_start["UNKNOWN"], "passed": existing_by_class_passed["UNKNOWN"]},
        }
    }

    remaining_items = items[start_idx:]
    sem = asyncio.Semaphore(CONCURRENCY)
    queue = asyncio.Queue(maxsize=2000)
    lock = asyncio.Lock()

    # Append to OUT_REAL_POOL
    with open(OUT_REAL_POOL, "a", encoding="utf-8") as out_fp:
        workers = [asyncio.create_task(worker(queue, sem, out_fp, stats, total_pool_size, lock, existing_passed_set)) for _ in range(CONCURRENCY)]

        for it in remaining_items:
            await queue.put(it)

        await queue.join()

        for _ in range(CONCURRENCY):
            await queue.put(None)
        await asyncio.gather(*workers)

    # Clean deduplication pass on OUT_REAL_POOL
    dedup_lines = {}
    with open(OUT_REAL_POOL, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            addr = line.split("\t")[0].strip()
            if ":" in addr and addr not in dedup_lines:
                dedup_lines[addr] = line

    with open(OUT_REAL_POOL, "w", encoding="utf-8") as f:
        for addr in sorted(dedup_lines.keys()):
            f.write(dedup_lines[addr] + "\n")

    final_unique_count = len(dedup_lines)

    dt = time.time() - stats["start_time"]
    print("=" * 80)
    print("RE-VERIFICATION 100% COMPLETE")
    print(f"Total Master Pool Tested: {total_pool_size:,}")
    print(f"Final Unique Genuine Survivors in real_pool.txt: {final_unique_count:,}")
    print(f"Overall Genuine Pass Rate: {(final_unique_count / total_pool_size)*100:.2f}%")
    print("-" * 80)
    print("FINAL GENUINE RATE PER ASN CLASS:")
    summary_by_class = {}
    for cls in ["RESIDENTIAL", "DATACENTER", "MOBILE", "UNKNOWN"]:
        t = stats["by_class"][cls]["tested"]
        p = stats["by_class"][cls]["passed"]
        rate = (p / max(1, t)) * 100
        summary_by_class[cls] = {"tested": t, "passed": p, "rate_pct": round(rate, 2)}
        print(f"  {cls:<14}: {p:6,} passed / {t:7,} tested ({rate:5.2f}%)")
    print("=" * 80)

    # Save summary json
    summary_data = {
        "total_tested": total_pool_size,
        "final_unique_survivors": final_unique_count,
        "overall_pass_rate_pct": round((final_unique_count / total_pool_size) * 100, 2),
        "by_class": summary_by_class,
        "real_pool_path": OUT_REAL_POOL
    }
    with open(SUMMARY_FILE, "w", encoding="utf-8") as sf:
        json.dump(summary_data, sf, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
