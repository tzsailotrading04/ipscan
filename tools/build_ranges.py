#!/usr/bin/env python3
"""
tools/build_ranges.py
Top-up Range Queue Daemon:
- Sourced exclusively from 11 target hosting ASNs via the RIPEstat announced-prefixes API:
    AS16276 OVH, AS24940 Hetzner, AS51167 Contabo, AS20473 Vultr,
    AS63949 Linode, AS14061 DigitalOcean, AS28753 & AS60781 Leaseweb,
    AS9009 M247, AS36352 ColoCrossing, AS47583 Hostinger.
- AWS, GCP, and Azure are completely dropped.
- Emits IPs into chunked files: q_a0_hosting_<ts>_<nn>.txt of 500,000 lines.
- Maintains queue depth >= 15,000,000 lines.
- Persists progress in work/ranges_cursor.json.
- Deletes consumed queue files.
- With --once: runs one full check/top-up cycle and exits.
"""

import os
import sys
import time
import json
import re
import urllib.request
import ipaddress
import datetime

REPO_ROOT = r"D:\DEpinFarm" if os.path.exists(r"D:\DEpinFarm") else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEAD_FILE = os.path.join(REPO_ROOT, "cache", "pool_dead.txt")
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
QUEUE_DIR = os.path.join(REPO_ROOT, "ip", "harvest", "queue")
ACKS_DIR = os.path.join(REPO_ROOT, "ip", "harvest", "acks")
QCUR_DIR = os.path.join(REPO_ROOT, "cache", "qcursor")
WORK_DIR = os.path.join(REPO_ROOT, "work")
CURSOR_FILE = os.path.join(WORK_DIR, "ranges_cursor.json")

TARGET_ASNS = [
    ("AS16276", "OVH"),
    ("AS24940", "Hetzner"),
    ("AS51167", "Contabo"),
    ("AS20473", "Vultr"),
    ("AS63949", "Linode"),
    ("AS14061", "DigitalOcean"),
    ("AS28753", "Leaseweb"),
    ("AS60781", "Leaseweb"),
    ("AS9009", "M247"),
    ("AS36352", "ColoCrossing"),
    ("AS47583", "Hostinger"),
]

CHUNK_SIZE = 500000
TARGET_QUEUE_DEPTH = 15000000
NUM_SHARDS = 20

def fetch_json(url, headers=None, timeout=30):
    hdr = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    if headers:
        hdr.update(headers)
    req = urllib.request.Request(url, headers=hdr)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def fetch_asn_prefixes(asn_tuple):
    asn, name = asn_tuple
    url = f"https://stat.ripe.net/data/announced-prefixes/data.json?resource={asn}"
    try:
        raw = fetch_json(url)
        data = json.loads(raw)
        prefixes = data.get("data", {}).get("prefixes", [])
        v4_nets = []
        for p_obj in prefixes:
            p = p_obj.get("prefix", "")
            if ":" not in p and "/" in p:
                try:
                    v4_nets.append(ipaddress.ip_network(p, strict=False))
                except Exception:
                    pass
        collapsed = list(ipaddress.collapse_addresses(set(v4_nets)))
        total_ips = sum(n.num_addresses for n in collapsed)
        return {
            "asn": asn,
            "name": name,
            "networks": collapsed,
            "prefix_count": len(collapsed),
            "total_ips": total_ips
        }
    except Exception as e:
        print(f"[WARN] Failed fetching prefixes for {asn} ({name}): {e}", file=sys.stderr, flush=True)
        return {
            "asn": asn,
            "name": name,
            "networks": [],
            "prefix_count": 0,
            "total_ips": 0
        }

def fetch_all_asn_networks():
    asn_stats = []
    all_raw_nets = []
    for asn_entry in TARGET_ASNS:
        res = fetch_asn_prefixes(asn_entry)
        asn_stats.append(res)
        all_raw_nets.extend(res["networks"])

    grand_collapsed = list(ipaddress.collapse_addresses(set(all_raw_nets)))
    grand_total_ips = sum(n.num_addresses for n in grand_collapsed)
    return grand_collapsed, asn_stats, grand_total_ips

def load_subtracted_ips():
    subtracted = set()
    if os.path.exists(DEAD_FILE):
        with open(DEAD_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                for tok in line.split():
                    if ":" in tok and not tok.startswith("["):
                        subtracted.add(tok.split(":")[0].strip())
                        break
                    elif re.match(r'^(?:\d{1,3}\.){3}\d{1,3}$', tok):
                        subtracted.add(tok)
                        break

    if os.path.exists(POOL_FILE):
        with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line:
                    first_tok = line.split("\t")[0].split()[0]
                    ip = first_tok.split(":")[0].strip()
                    if ip:
                        subtracted.add(ip)
    return subtracted

def count_queue_lines():
    if not os.path.exists(QUEUE_DIR):
        return 0
    total = 0
    for f in os.listdir(QUEUE_DIR):
        if f.startswith("q_") and f.endswith(".txt"):
            p = os.path.join(QUEUE_DIR, f)
            try:
                total += sum(1 for _ in open(p, "rb"))
            except Exception:
                pass
    return total

def cleanup_consumed_files():
    deleted_count = 0
    if not os.path.exists(QUEUE_DIR):
        return 0

    for f in os.listdir(QUEUE_DIR):
        if not (f.startswith("q_") and f.endswith(".txt")):
            continue
        qf_path = os.path.join(QUEUE_DIR, f)

        # Check 1: Empty file
        try:
            if os.path.getsize(qf_path) == 0:
                os.remove(qf_path)
                deleted_count += 1
                continue
        except Exception:
            pass

        # Check 2: Acknowledged by all NUM_SHARDS
        is_consumed = False
        if os.path.exists(ACKS_DIR):
            acks = [a for a in os.listdir(ACKS_DIR) if a.startswith(f"{f}.ack_") and not a.endswith(".tmp")]
            if len(acks) >= NUM_SHARDS:
                is_consumed = True
                for a in acks:
                    try: os.remove(os.path.join(ACKS_DIR, a))
                    except Exception: pass

        # Check 3: All shard cursors DONE
        if not is_consumed and os.path.exists(QCUR_DIR):
            all_done = True
            for s in range(NUM_SHARDS):
                cp = os.path.join(QCUR_DIR, f"{f}.cur_{s}")
                if not (os.path.exists(cp) and open(cp, "r", encoding="utf-8", errors="ignore").read().strip() == "DONE"):
                    all_done = False
                    break
            if all_done:
                is_consumed = True
                for s in range(NUM_SHARDS):
                    cp = os.path.join(QCUR_DIR, f"{f}.cur_{s}")
                    try: os.remove(cp)
                    except Exception: pass

        if is_consumed:
            try:
                os.remove(qf_path)
                deleted_count += 1
            except Exception:
                pass

    return deleted_count

def load_cursor():
    os.makedirs(WORK_DIR, exist_ok=True)
    if os.path.exists(CURSOR_FILE):
        try:
            with open(CURSOR_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return {"cursor": 0, "total_emitted": 0, "file_seq": 1}

def save_cursor(state):
    os.makedirs(WORK_DIR, exist_ok=True)
    try:
        with open(CURSOR_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(CURSOR_FILE + ".tmp", CURSOR_FILE)
    except Exception:
        pass

class AddressStream:
    def __init__(self, networks, subtracted_ips, start_cursor=0):
        self.networks = networks
        self.subtracted = subtracted_ips
        self.cursor = start_cursor
        self.current_idx = 0
        self.net_idx = 0
        self.net_offset = 0

        # Fast-forward to start_cursor
        traversed = 0
        for i, net in enumerate(self.networks):
            net_sz = net.num_addresses if net.prefixlen >= 31 else (net.num_addresses - 2)
            if net_sz <= 0:
                net_sz = 1
            if traversed + net_sz <= start_cursor:
                traversed += net_sz
            else:
                self.net_idx = i
                self.net_offset = start_cursor - traversed
                self.current_idx = start_cursor
                break
        else:
            self.net_idx = 0
            self.net_offset = 0
            self.current_idx = 0

    def next_ip(self):
        while self.net_idx < len(self.networks):
            net = self.networks[self.net_idx]
            net_sz = net.num_addresses if net.prefixlen >= 31 else (net.num_addresses - 2)
            if net_sz <= 0:
                net_sz = 1

            start_ip_int = int(net.network_address)
            if net.prefixlen < 31:
                start_ip_int += 1  # Skip network address

            while self.net_offset < net_sz:
                ip_int = start_ip_int + self.net_offset
                self.net_offset += 1
                self.cursor += 1
                ip_str = str(ipaddress.IPv4Address(ip_int))
                if ip_str not in self.subtracted:
                    return ip_str

            self.net_idx += 1
            self.net_offset = 0

        # Wrap around to start if space exhausted
        self.net_idx = 0
        self.net_offset = 0
        return self.next_ip()

def run_topup_cycle(networks, subtracted_ips):
    os.makedirs(QUEUE_DIR, exist_ok=True)
    os.makedirs(WORK_DIR, exist_ok=True)

    files_deleted = cleanup_consumed_files()
    queue_depth = count_queue_lines()
    cursor_state = load_cursor()
    cursor_val = cursor_state.get("cursor", 0)

    files_added = 0
    stream = AddressStream(networks, subtracted_ips, start_cursor=cursor_val)

    if queue_depth < TARGET_QUEUE_DEPTH:
        ts = int(time.time())
        file_seq = cursor_state.get("file_seq", 1)

        while queue_depth < TARGET_QUEUE_DEPTH:
            chunk = []
            while len(chunk) < CHUNK_SIZE:
                ip = stream.next_ip()
                chunk.append(ip)

            out_filename = f"q_a0_hosting_{ts}_{file_seq:02d}.txt"
            out_path = os.path.join(QUEUE_DIR, out_filename)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n".join(chunk) + "\n")

            files_added += 1
            file_seq += 1
            queue_depth += len(chunk)

        cursor_state["cursor"] = stream.cursor
        cursor_state["total_emitted"] = cursor_state.get("total_emitted", 0) + (files_added * CHUNK_SIZE)
        cursor_state["file_seq"] = file_seq
        cursor_state["last_ts"] = ts
        save_cursor(cursor_state)

    iso_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"{iso_time} queue_depth={queue_depth:,} files_added={files_added} files_deleted={files_deleted} ranges_cursor={cursor_state['cursor']:,}", flush=True)
    return queue_depth, files_added, files_deleted, cursor_state["cursor"]

def clear_existing_hosting_files():
    if not os.path.exists(QUEUE_DIR):
        return 0
    cleared = 0
    for f in os.listdir(QUEUE_DIR):
        if f.startswith("q_a0_hosting_") and f.endswith(".txt"):
            try:
                os.remove(os.path.join(QUEUE_DIR, f))
                cleared += 1
            except Exception:
                pass
    # Also clean up related acks and cursor files
    if os.path.exists(ACKS_DIR):
        for f in os.listdir(ACKS_DIR):
            if f.startswith("q_a0_hosting_"):
                try: os.remove(os.path.join(ACKS_DIR, f))
                except Exception: pass
    if os.path.exists(QCUR_DIR):
        for f in os.listdir(QCUR_DIR):
            if f.startswith("q_a0_hosting_"):
                try: os.remove(os.path.join(QCUR_DIR, f))
                except Exception: pass

    # Reset ranges cursor
    if os.path.exists(CURSOR_FILE):
        try: os.remove(CURSOR_FILE)
        except Exception: pass

    return cleared

def main():
    print("Initializing ASN Range Top-up Engine (Fetching announced prefixes via RIPEstat)...", flush=True)
    networks, asn_stats, grand_total = fetch_all_asn_networks()
    subtracted = load_subtracted_ips()

    print("\n" + "=" * 65)
    print("ANNOUNCED PREFIX AND ADDRESS COUNTS PER TARGET ASN:")
    print("-" * 65)
    for stat in asn_stats:
        print(f"  {stat['asn']:<8} {stat['name']:<15} | Prefixes: {stat['prefix_count']:<6} | Addresses: {stat['total_ips']:,}")
    print("-" * 65)
    print(f"  TOTAL COMBINED COLLAPSED SPACE : {len(networks):<6} prefixes | {grand_total:,} addresses")
    print("=" * 65 + "\n")

    if "--clear" in sys.argv:
        cleared = clear_existing_hosting_files()
        print(f"Cleared {cleared} existing q_a0_hosting_* queue files and reset ranges cursor.\n", flush=True)

    if "--once" in sys.argv:
        run_topup_cycle(networks, subtracted)
        return

    print("Starting background top-up daemon (Interval: 60s, Target: 15M lines)...", flush=True)
    while True:
        try:
            run_topup_cycle(networks, subtracted)
        except Exception as e:
            print(f"[ERROR] Exception in top-up cycle: {e}", file=sys.stderr, flush=True)
        time.sleep(60)

if __name__ == "__main__":
    main()
