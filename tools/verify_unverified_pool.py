"""
tools/verify_unverified_pool.py
Strictly re-verifies all unverified candidates from:
- All shard parts (ip/harvest/verified_alive_part_*.txt)
- master_pool.txt
- ip/public_pool.txt, ip/public_dc.txt
- ip/harvest/backup_pool_20261028_182133.txt

Strict criteria:
- HTTP 200 on CONNECT
- Valid TLS ClientHello with SNI matching target
- Strict ServerHello 0x16 byte
- Full TLS handshake verified against System CA chain (getpeercert())
- Targets: speed.cloudflare.com, www.google.com, one.one.one.one
- Appends genuine survivors with ASN categorization to ip/harvest/real_pool.txt
"""
import asyncio
import bisect
import glob
import json
import os
import random
import socket
import ssl
import struct
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = r"D:\DEpinFarm"
REAL_POOL_FILE = os.path.join(ROOT, "ip", "harvest", "real_pool.txt")
SEEN_FILE = os.path.join(ROOT, "cache", "harvest_seen_set.txt")
ASN_FILE = os.path.join(ROOT, "data", "ip2asn-v4-u32.tsv")

TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
SSL_CTX = ssl.create_default_context()

CONCURRENCY = 400
TIMEOUT = 3.5

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
    if not os.path.exists(ASN_FILE):
        return [], []
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
    return rows, starts

asn_rows, asn_starts = load_asn_table()

def classify_ip(ip_str):
    if not asn_rows:
        return "UNKNOWN", "0", "UNKNOWN"
    try:
        u = ip_to_u32(ip_str)
    except Exception:
        return "UNKNOWN", "0", "UNKNOWN"
    i = bisect.bisect_right(asn_starts, u) - 1
    if i >= 0 and asn_rows[i][0] <= u <= asn_rows[i][1]:
        asn, cc, org = asn_rows[i][2], asn_rows[i][3], asn_rows[i][4]
        org_l = org.lower()
        if any(m in org_l for m in MOB_SUBS):
            return "MOBILE", asn, org
        if any(d in org_l for d in DC_SUBS):
            return "DATACENTER", asn, org
        if any(isp in org_l for isp in ISP_SUBS):
            return "RESIDENTIAL", asn, org
        return "UNKNOWN", asn, org
    return "UNKNOWN", "0", "UNKNOWN"

def sync_tls_handshake(sock, target, timeout=3.5):
    try:
        sock.setblocking(True)
        sock.settimeout(timeout)
        req = f"CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\n\r\n".encode()
        sock.sendall(req)
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = sock.recv(512)
            if not chunk: return False
            resp += chunk
            if len(resp) > 2048: return False

        first_line = resp.split(b"\r\n")[0]
        if not (b" 200" in first_line or b"HTTP/1.1 200" in first_line or b"HTTP/1.0 200" in first_line):
            return False

        ss = SSL_CTX.wrap_socket(sock, server_hostname=target)
        ss.settimeout(timeout)
        ss.do_handshake()
        cert = ss.getpeercert()
        if not cert:
            ss.close()
            return False
        ss.close()
        return True
    except Exception:
        try: sock.close()
        except Exception: pass
        return False

def sync_probe_candidate(ip_port):
    try:
        ip, port_s = ip_port.split(":", 1)
        port = int(port_s)
    except Exception:
        return ip_port, False, None, None

    for target in TARGETS:
        s = None
        try:
            s = socket.create_connection((ip, port), timeout=TIMEOUT)
            if sync_tls_handshake(s, target, timeout=TIMEOUT):
                asn_class, asn_num, org = classify_ip(ip)
                return ip_port, True, target, f"{asn_class}\t{asn_num}\t{org}"
        except Exception:
            if s:
                try: s.close()
                except Exception: pass
    return ip_port, False, None, None

def load_file_set(path):
    s = set()
    if os.path.exists(path):
        for line in open(path, errors="ignore"):
            l = line.strip()
            if l and not l.startswith("#"):
                ip_port = l.split()[0].split("\t")[0]
                if ":" in ip_port:
                    s.add(ip_port)
    return s

def main():
    print("=" * 75)
    print("STRICT CERT-VALID POOL EXPANSION ENGINE")
    print("=" * 75)

    # 1. Load current real pool to preserve and exclude
    existing_pool = load_file_set(REAL_POOL_FILE)
    print(f"Loaded existing real pool: {len(existing_pool):,} verified survivors")

    # 2. Gather candidates from all known sources
    print("Gathering candidates from all shard parts, master pool, and public pools...")
    candidates_set = set()

    # Priority 1: Shard parts
    shard_parts = glob.glob(os.path.join(ROOT, "ip", "harvest", "verified_alive_part_*.txt"))
    for sp in shard_parts:
        candidates_set.update(load_file_set(sp))
    print(f"  Shard parts ({len(shard_parts)} files): {len(candidates_set):,} unique candidates")

    # Priority 2: Master pool
    m_pool = load_file_set(os.path.join(ROOT, "master_pool.txt"))
    candidates_set.update(m_pool)
    print(f"  + Master pool: Total now {len(candidates_set):,} unique candidates")

    # Priority 3: Public pools
    p_pool = load_file_set(os.path.join(ROOT, "ip", "public_pool.txt"))
    candidates_set.update(p_pool)
    p_dc = load_file_set(os.path.join(ROOT, "ip", "public_dc.txt"))
    candidates_set.update(p_dc)
    print(f"  + Public pools: Total now {len(candidates_set):,} unique candidates")

    # Filter out already in real_pool
    candidates = list(candidates_set - existing_pool)
    # Shuffle so we get diverse ASNs and ports across the space
    random.seed(42)
    random.shuffle(candidates)

    print(f"\nTotal novel candidates to verify: {len(candidates):,}")
    print(f"Concurrency: {CONCURRENCY} workers | Timeout: {TIMEOUT}s | Targets: {TARGETS}")
    print("=" * 75)

    t0 = time.time()
    done = 0
    survivors_found = 0
    total = len(candidates)
    batch_survivors = []

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        for ip_port, ok, target, asn_info in executor.map(sync_probe_candidate, candidates):
            done += 1
            if ok:
                survivors_found += 1
                record = f"{ip_port}\t{target}\t{asn_info}"
                batch_survivors.append(record)
                existing_pool.add(ip_port)

                # Write survivor immediately
                with open(REAL_POOL_FILE, "a", encoding="utf-8") as f:
                    f.write(f"{record}\n")

            if done % 1000 == 0 or done == total:
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                pct = done / total * 100
                surv_pct = survivors_found / done * 100
                total_pool_now = len(existing_pool)
                print(f"[{done:,}/{total:,} ({pct:.1f}%)] ({rate:.1f} prx/s) | +{survivors_found:,} NEW Survivors ({surv_pct:.2f}%) | Real Pool Total: {total_pool_now:,}", flush=True)

    elapsed_total = time.time() - t0
    print("\n" + "=" * 75)
    print("VERIFICATION COMPLETED")
    print(f"Total Processed: {done:,} candidates in {elapsed_total/60:.1f} mins ({done/elapsed_total:.1f} prx/s)")
    print(f"New Strict Survivors Added: +{survivors_found:,}")
    print(f"Final Real Pool Total     : {len(existing_pool):,}")
    print("=" * 75)

if __name__ == "__main__":
    main()
