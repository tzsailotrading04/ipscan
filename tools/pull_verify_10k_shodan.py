"""
tools/pull_verify_10k_shodan.py
Samples 10,000 random Shodan InternetDB candidates (Datacenter only, no residential),
strict-verifies all 10,000 using the multi-target TLS 0x16 probe,
and reports pass count, pass rate, and breakdown by port and provider.
"""
import asyncio
import bisect
import glob
import os
import random
import socket
import ssl
import struct
import sys
import time
from collections import Counter

ROOT = r"D:\DEpinFarm"
ASN_FILE = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")
SAMPLE_OUT = os.path.join(ROOT, "work", "sample_10k_shodan_datacenter.txt")
REPORT_OUT = os.path.join(ROOT, "work", "SHODAN_10K_REPORT.txt")
PASSED_OUT = os.path.join(ROOT, "work", "shodan_10k_passed.txt")

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

def sample_10k_shodan_candidates():
    print("Gathering candidate pool from shodan_shard_v98_*.txt...")
    t0 = time.time()
    files = sorted(glob.glob(os.path.join(ROOT, "ip", "harvest", "shodan_shard_v98_*.txt")))
    # Exclude backup or non-primary files if any
    files = [f for f in files if not f.endswith(".bak") and not f.endswith(".tmp")]
    print(f"Reading from {len(files)} shodan shard files...")
    
    # We want 10,000 random datacenter candidates.
    # To sample fairly across all shards, we pick random lines from each file.
    candidates_pool = []
    lines_scanned = 0
    dc_found = 0

    for f_idx, fpath in enumerate(files):
        # Sample lines from each file
        with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
            for l_idx, line in enumerate(fp):
                lines_scanned += 1
                # Sample stride or random pick
                if (l_idx + f_idx) % 7 == 0:
                    line = line.strip()
                    if line and ":" in line:
                        ip = line.split(":")[0]
                        # Quick check
                        cat, asn, org = classify_ip(ip)
                        if cat == "DATACENTER":
                            candidates_pool.append((line, org))
                            dc_found += 1
                            if len(candidates_pool) >= 40000:
                                break
        if len(candidates_pool) >= 40000:
            break

    print(f"Scanned {lines_scanned:,} lines, found {dc_found:,} datacenter candidates in {time.time()-t0:.2f}s")
    
    # Shuffle and pick exactly 10,000
    random.seed(42) # Deterministic for reproducibility
    random.shuffle(candidates_pool)
    sample_10k = candidates_pool[:10000]
    
    os.makedirs(os.path.dirname(SAMPLE_OUT), exist_ok=True)
    with open(SAMPLE_OUT, "w", encoding="utf-8") as out:
        for p, org in sample_10k:
            out.write(f"{p}\t{org}\n")
    print(f"Saved exactly {len(sample_10k):,} datacenter candidates to {SAMPLE_OUT}")
    return sample_10k

# Strict TLS probe
async def inline_probe_connected(s, target, timeout=5.0):
    try:
        loop = asyncio.get_running_loop()
        req = f"CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\n\r\n".encode()
        await loop.sock_sendall(s, req)
        resp = b""
        t_end = time.monotonic() + timeout
        while b"\r\n\r\n" not in resp:
            if time.monotonic() > t_end:
                return False
            c = await asyncio.wait_for(loop.sock_recv(s, 512), timeout=timeout)
            if not c:
                return False
            resp += c
        first_line = resp.split(b"\r\n")[0]
        if not (resp.startswith(b"HTTP/") and (b" 200" in first_line or b" 2" in first_line)):
            return False
        parts = resp.split(b"\r\n\r\n", 1)
        trailing = parts[1] if len(parts) > 1 else b""
        if trailing:
            return trailing[:1] == b"\x16"
        await loop.sock_sendall(s, CLIENT_HELLOS[target])
        b1 = await asyncio.wait_for(loop.sock_recv(s, 1), timeout=timeout)
        return b1 == b"\x16"
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

async def strict_verify_proxy(ip_port, org, sem, progress_tracker):
    async with sem:
        try:
            ip, port_s = ip_port.split(":", 1)
            port = int(port_s)
        except Exception:
            progress_tracker["done"] += 1
            return ip_port, org, False, "BAD_FMT"

        loop = asyncio.get_running_loop()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(False)
        try:
            await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=1.8)
        except Exception:
            try:
                s.close()
            except Exception:
                pass
            progress_tracker["done"] += 1
            return ip_port, org, False, "CONNECT_FAIL"

        # Multi-target check with 0x16 ServerHello
        passed = False
        target_hit = ""
        if await inline_probe_connected(s, "speed.cloudflare.com", timeout=5.0):
            passed = True
            target_hit = "speed.cloudflare.com"
        else:
            for t in ["www.google.com", "one.one.one.one"]:
                if await probe_single_target(ip, port, t, timeout=5.0):
                    passed = True
                    target_hit = t
                    break

        progress_tracker["done"] += 1
        if passed:
            progress_tracker["pass"] += 1

        if progress_tracker["done"] % 1000 == 0:
            print(f"[{progress_tracker['done']:,}/10,000] Verified | Passed so far: {progress_tracker['pass']:,} ({progress_tracker['pass']/progress_tracker['done']*100:.2f}%)")

        return ip_port, org, passed, target_hit if passed else "TLS_FAIL"

async def run_verification():
    sample_10k = sample_10k_shodan_candidates()
    print(f"\nStarting strict verification of {len(sample_10k):,} candidates at CONCURRENCY = 250...")
    t0 = time.time()
    
    sem = asyncio.Semaphore(250)
    progress_tracker = {"done": 0, "pass": 0}
    
    tasks = [strict_verify_proxy(p, org, sem, progress_tracker) for p, org in sample_10k]
    results = await asyncio.gather(*tasks)
    
    elapsed = time.time() - t0
    rate = len(sample_10k) / elapsed
    
    passed_items = [r for r in results if r[2]]
    pass_count = len(passed_items)
    pass_rate = (pass_count / len(sample_10k)) * 100.0
    
    # Breakdowns
    port_counter = Counter()
    prov_counter = Counter()
    prov_total = Counter()
    for ip_port, org, ok, target in results:
        port = ip_port.split(":", 1)[1]
        prov = org.split()[0].upper().strip(",.-")
        prov_total[prov] += 1
        if ok:
            port_counter[port] += 1
            prov_counter[prov] += 1

    # Save passed proxies
    with open(PASSED_OUT, "w", encoding="utf-8") as pf:
        for ip_port, org, ok, target in passed_items:
            pf.write(f"{ip_port}\t{target}\tDATACENTER\t0\t{org}\n")

    # Format Report
    report = []
    report.append("=" * 80)
    report.append("STRICT VERIFICATION REPORT: 10,000 SHODAN INTERNETDB CANDIDATES")
    report.append("=" * 80)
    report.append(f"Target Mode          : DATACENTER ONLY (No Residential)")
    report.append(f"Probe Specification  : Strict Multi-Target TLS 0x16 (speed.cloudflare.com, google, 1.1.1.1)")
    report.append(f"Total Candidates     : {len(sample_10k):,}")
    report.append(f"Strict Pass Count    : {pass_count:,}")
    report.append(f"Strict Pass Rate     : {pass_rate:.4f}% ({pass_count}/{len(sample_10k):,})")
    report.append(f"Elapsed Time         : {elapsed:.2f} seconds ({rate:.1f} proxies/s)")
    report.append("-" * 80)
    report.append("PORT BREAKDOWN (Passed Survivors):")
    for port, count in port_counter.most_common():
        pct = (count / pass_count * 100.0) if pass_count > 0 else 0.0
        report.append(f"  Port {port:<6} : {count:>5} passed ({pct:5.1f}%)")
    report.append("-" * 80)
    report.append("TOP PROVIDER BREAKDOWN (Pass Rate):")
    report.append(f"  {'Provider':<22} {'Tested':<10} {'Passed':<10} {'Pass Rate':<12}")
    for prov, tot in prov_total.most_common(15):
        p_pass = prov_counter.get(prov, 0)
        p_pct = (p_pass / tot * 100.0) if tot > 0 else 0.0
        report.append(f"  {prov:<22} {tot:<10,} {p_pass:<10} {p_pct:5.2f}%")
    report.append("=" * 80)
    
    report_text = "\n".join(report)
    with open(REPORT_OUT, "w", encoding="utf-8") as rf:
        rf.write(report_text + "\n")
        
    print("\n" + report_text)

if __name__ == "__main__":
    asyncio.run(run_verification())
