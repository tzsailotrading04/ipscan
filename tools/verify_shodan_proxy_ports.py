"""
tools/verify_shodan_proxy_ports.py
1. Verifies 500 known-good proxies through the exact probe harness.
2. Filters Shodan InternetDB candidates to proxy ports only (excluding 80 and 443):
   [3128, 8080, 1080, 8888, 8081, 8083, 8087, 8090, 8181, 9000, 4444, 10000, 20000, 5000, 7000, 7001, 9999]
3. Samples 2,000 candidates from the filtered set.
4. Strict-verifies all 2,000 and reports pass count, overall pass rate, and pass rate per port.
"""
import argparse
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
KNOWN_GOOD_PATH = os.path.join(ROOT, "ip", "harvest", "test_500_known_good.txt")
SAMPLE_2K_OUT = os.path.join(ROOT, "work", "sample_2k_shodan_proxy_ports.txt")
REPORT_2K_OUT = os.path.join(ROOT, "work", "SHODAN_2K_REPORT.txt")

ALLOWED_PORTS = {
    3128, 8080, 1080, 8888, 8081, 8083, 8087, 8090, 8181,
    9000, 4444, 10000, 20000, 5000, 7000, 7001, 9999
}

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

asn_rows, asn_starts = [], []
def load_asn_table():
    global asn_rows, asn_starts
    if asn_starts: return
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
    asn_starts = [r[0] for r in rows]
    asn_rows = rows
    print(f"Loaded {len(rows):,} ASN ranges in {time.time()-t0:.2f}s", flush=True)

def classify_ip(ip_str):
    if not asn_starts:
        load_asn_table()
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

async def strict_verify_proxy(ip_port, sem, progress=None):
    async with sem:
        try:
            ip, port_s = ip_port.split(":", 1)
            port = int(port_s)
        except Exception:
            if progress: progress["done"] += 1
            return ip_port, False, "BAD_FMT"

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
            if progress: progress["done"] += 1
            return ip_port, False, "CONNECT_FAIL"

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

        if progress:
            progress["done"] += 1
            if passed: progress["pass"] += 1
            if progress["done"] % 500 == 0:
                print(f"[{progress['done']:,}/{progress['total']:,}] Verified | Passed: {progress['pass']:,} ({progress['pass']/progress['done']*100:.2f}%)", flush=True)

        return ip_port, passed, target_hit if passed else "TLS_FAIL"

async def test_known_good():
    print("=" * 80, flush=True)
    print("STEP 1: VERIFYING 500 KNOWN-GOOD PROXIES THROUGH THIS EXACT HARNESS", flush=True)
    print("=" * 80, flush=True)
    proxies = [l.strip().split()[0].split("\t")[0] for l in open(KNOWN_GOOD_PATH) if l.strip() and ":" in l]
    print(f"Loaded {len(proxies)} known-good proxies from {KNOWN_GOOD_PATH}", flush=True)
    sem = asyncio.Semaphore(250)
    tracker = {"done": 0, "pass": 0, "total": len(proxies)}
    t0 = time.time()
    results = await asyncio.gather(*[strict_verify_proxy(p, sem, tracker) for p in proxies])
    elapsed = time.time() - t0
    passed = [r for r in results if r[1]]
    pass_rate = len(passed) / len(proxies) * 100.0
    print(f"\nKNOWN-GOOD RESULTS:")
    print(f"  Tested     : {len(proxies)}")
    print(f"  Passed     : {len(passed)}")
    print(f"  Pass Rate  : {pass_rate:.2f}%")
    print(f"  Elapsed    : {elapsed:.2f}s ({(len(proxies)/elapsed):.1f} proxies/s)")
    fail_counts = Counter(r[2] for r in results if not r[1])
    print(f"  Failures   : {dict(fail_counts)}", flush=True)
    return len(passed), pass_rate

def sample_2k_proxy_ports():
    load_asn_table()
    print("\n" + "=" * 80, flush=True)
    print("STEP 2: FILTERING SHODAN CANDIDATES TO PROXY PORTS ONLY", flush=True)
    print(f"Allowed Proxy Ports : {sorted(ALLOWED_PORTS)}", flush=True)
    print("Excluded Ports      : 80, 443 completely", flush=True)
    print("Scope               : Datacenter only, no residential", flush=True)
    print("=" * 80, flush=True)
    
    files = sorted(glob.glob(os.path.join(ROOT, "ip", "harvest", "shodan_shard_v98_*.txt")))
    files = [f for f in files if not f.endswith(".bak") and not f.endswith(".tmp")]
    print(f"Scanning across {len(files)} shodan shard candidate files...", flush=True)

    pool = []
    t0 = time.time()
    lines_read = 0

    for fpath in files:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
            for line in fp:
                lines_read += 1
                line = line.strip()
                if not line or ":" not in line:
                    continue
                ip, port_s = line.split(":", 1)
                try:
                    port = int(port_s)
                except ValueError:
                    continue
                
                # STRICT PROXY PORT FILTER
                if port not in ALLOWED_PORTS:
                    continue
                
                # DATACENTER CHECK
                cat, asn, org = classify_ip(ip)
                if cat == "DATACENTER":
                    pool.append(line)
                    if len(pool) >= 15000:
                        break
        if len(pool) >= 15000:
            break

    print(f"Scanned {lines_read:,} lines in {time.time()-t0:.2f}s | Found {len(pool):,} matching candidates on proxy ports.", flush=True)
    
    # Shuffle and pick exactly 2,000
    random.seed(12345)
    random.shuffle(pool)
    sample_2k = pool[:2000]
    
    with open(SAMPLE_2K_OUT, "w", encoding="utf-8") as out:
        for p in sample_2k:
            out.write(f"{p}\n")
    print(f"Saved exactly {len(sample_2k):,} candidates to {SAMPLE_2K_OUT}", flush=True)
    return sample_2k

async def verify_2k_candidates(sample_2k):
    print("\n" + "=" * 80, flush=True)
    print("STEP 3: STRICT VERIFICATION OF 2,000 FILTERED CANDIDATES", flush=True)
    print("=" * 80, flush=True)
    
    sem = asyncio.Semaphore(250)
    tracker = {"done": 0, "pass": 0, "total": len(sample_2k)}
    t0 = time.time()
    
    results = await asyncio.gather(*[strict_verify_proxy(p, sem, tracker) for p in sample_2k])
    elapsed = time.time() - t0
    rate = len(sample_2k) / elapsed
    
    passed_items = [r for r in results if r[1]]
    pass_count = len(passed_items)
    pass_rate = (pass_count / len(sample_2k)) * 100.0
    
    # Port-by-port breakdown
    port_tested = Counter()
    port_passed = Counter()
    for ip_port, ok, reason in results:
        port = int(ip_port.split(":", 1)[1])
        port_tested[port] += 1
        if ok:
            port_passed[port] += 1
            
    report = []
    report.append("=" * 80)
    report.append("STRICT VERIFICATION REPORT: 2,000 SHODAN PROXY-PORT CANDIDATES")
    report.append("=" * 80)
    report.append(f"Proxy Ports Tested   : {sorted(ALLOWED_PORTS)}")
    report.append(f"Excluded Ports       : 80, 443 (Zero tested)")
    report.append(f"Total Candidates     : {len(sample_2k):,}")
    report.append(f"Strict Pass Count    : {pass_count:,}")
    report.append(f"Strict Pass Rate     : {pass_rate:.4f}% ({pass_count}/{len(sample_2k):,})")
    report.append(f"Elapsed Time         : {elapsed:.2f} seconds ({rate:.1f} proxies/s)")
    report.append("-" * 80)
    report.append("PASS RATE PER PORT:")
    report.append(f"  {'Port':<10} {'Tested':<10} {'Passed':<10} {'Pass Rate':<12}")
    report.append("-" * 80)
    for port in sorted(ALLOWED_PORTS):
        tested = port_tested[port]
        passed = port_passed[port]
        pct = (passed / tested * 100.0) if tested > 0 else 0.0
        report.append(f"  {port:<10} {tested:<10} {passed:<10} {pct:6.2f}%")
    report.append("=" * 80)
    
    report_text = "\n".join(report)
    with open(REPORT_2K_OUT, "w", encoding="utf-8") as rf:
        rf.write(report_text + "\n")
    print("\n" + report_text, flush=True)

async def main():
    # 1. Run 500 known-good test
    kg_pass, kg_rate = await test_known_good()
    
    # 2 & 3. Sample 2,000 and verify
    sample_2k = sample_2k_proxy_ports()
    await verify_2k_candidates(sample_2k)

if __name__ == "__main__":
    asyncio.run(main())
