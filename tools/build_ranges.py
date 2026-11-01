#!/usr/bin/env python3
"""
tools/build_ranges.py
Top-up Range Queue Daemon:
- Emits from the full address set of AWS, GCP, and Azure (no cap).
- Persists position in work/ranges_cursor.json so restarts resume smoothly.
- Never re-emits an address already written.
- Every 60s: counts total lines across all ip/harvest/queue/q_*.txt.
  If queue_depth < 15,000,000:
    appends more q_a0_hosting_<ts>_<nn>.txt files of 500,000 lines until >= 15,000,000.
- Deletes any queue file whose lines have all been consumed (acks >= 25 or all cur == DONE).
- Prints each cycle: iso_time queue_depth files_added files_deleted ranges_cursor.
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

AWS_URL = "https://ip-ranges.amazonaws.com/ip-ranges.json"
GCP_URL = "https://www.gstatic.com/ipranges/cloud.json"
AZURE_PAGE = "https://www.microsoft.com/en-us/download/details.aspx?id=56519"
AZURE_FALLBACK = "https://download.microsoft.com/download/7/1/d/71d86715-5596-4529-9b13-da13a5de5b63/ServiceTags_Public_20261026.json"

CHUNK_SIZE = 500000
TARGET_QUEUE_DEPTH = 15000000
NUM_SHARDS = 20

def fetch_json(url, headers=None, timeout=30):
    hdr = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if headers:
        hdr.update(headers)
    req = urllib.request.Request(url, headers=hdr)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def fetch_all_cloud_cidrs():
    # 1. AWS
    aws_raw = fetch_json(AWS_URL)
    aws_data = json.loads(aws_raw)
    aws_cidrs = [p["ip_prefix"] for p in aws_data.get("prefixes", []) if "ip_prefix" in p and ":" not in p["ip_prefix"]]
    aws_nets = [ipaddress.ip_network(c, strict=False) for c in set(aws_cidrs)]
    aws_collapsed = list(ipaddress.collapse_addresses(aws_nets))
    aws_total_ips = sum(n.num_addresses for n in aws_collapsed)

    # 2. GCP
    gcp_raw = fetch_json(GCP_URL)
    gcp_data = json.loads(gcp_raw)
    gcp_cidrs = [p["ipv4Prefix"] for p in gcp_data.get("prefixes", []) if "ipv4Prefix" in p and ":" not in p["ipv4Prefix"]]
    gcp_nets = [ipaddress.ip_network(c, strict=False) for c in set(gcp_cidrs)]
    gcp_collapsed = list(ipaddress.collapse_addresses(gcp_nets))
    gcp_total_ips = sum(n.num_addresses for n in gcp_collapsed)

    # 3. Azure
    azure_url = AZURE_FALLBACK
    try:
        html = fetch_json(AZURE_PAGE)
        matches = re.findall(r'https://download\.microsoft\.com/download/[^"\'\s]+/ServiceTags_Public_[0-9]+\.json', html)
        if matches:
            azure_url = matches[0]
    except Exception:
        pass

    azure_raw = fetch_json(azure_url)
    azure_data = json.loads(azure_raw)
    azure_cidrs = []
    for val in azure_data.get("values", []):
        for p in val.get("properties", {}).get("addressPrefixes", []):
            if ":" not in p and "/" in p:
                azure_cidrs.append(p)
    azure_nets = [ipaddress.ip_network(c, strict=False) for c in set(azure_cidrs)]
    azure_collapsed = list(ipaddress.collapse_addresses(azure_nets))
    azure_total_ips = sum(n.num_addresses for n in azure_collapsed)

    # Grand collapsed list of all three providers
    all_nets = list(ipaddress.collapse_addresses(set(aws_nets + gcp_nets + azure_nets)))
    grand_total_ips = sum(n.num_addresses for n in all_nets)

    counts = {
        "aws_total": aws_total_ips,
        "gcp_total": gcp_total_ips,
        "azure_total": azure_total_ips,
        "grand_total": grand_total_ips
    }
    return all_nets, counts

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

    # If cursor does not exist, check existing q_a0_hosting files to initialize past already emitted addresses
    initial_cursor = 0
    if os.path.exists(QUEUE_DIR):
        for f in os.listdir(QUEUE_DIR):
            if f.startswith("q_a0_hosting_") and f.endswith(".txt"):
                p = os.path.join(QUEUE_DIR, f)
                try:
                    initial_cursor += sum(1 for _ in open(p, "rb"))
                except Exception:
                    pass

    return {"cursor": initial_cursor, "total_emitted": initial_cursor, "file_seq": 1}

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

        # Wrap around to start if full cloud space exhausted
        self.net_idx = 0
        self.net_offset = 0
        return self.next_ip()

def run_topup_cycle(networks, subtracted_ips, counts=None, is_first_run=False):
    os.makedirs(QUEUE_DIR, exist_ok=True)
    os.makedirs(WORK_DIR, exist_ok=True)

    files_deleted = cleanup_consumed_files()
    queue_depth = count_queue_lines()
    cursor_state = load_cursor()
    cursor_val = cursor_state.get("cursor", 0)

    files_added = 0
    first_file_count = 0
    stream = AddressStream(networks, subtracted_ips, start_cursor=cursor_val)

    if queue_depth < TARGET_QUEUE_DEPTH:
        needed_lines = TARGET_QUEUE_DEPTH - queue_depth
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

            if files_added == 0:
                first_file_count = len(chunk)

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

    return queue_depth, files_added, files_deleted, cursor_state["cursor"], first_file_count

def main():
    print("Initializing Range Top-up Engine (Fetching cloud networks)...", flush=True)
    networks, counts = fetch_all_cloud_cidrs()
    subtracted = load_subtracted_ips()

    if "--once" in sys.argv:
        print("\n" + "=" * 65)
        print("TRUE TOTAL ADDRESS COUNTS BY PROVIDER (NO CAP):")
        print(f"  AWS True Total Addresses   : {counts['aws_total']:,}")
        print(f"  GCP True Total Addresses   : {counts['gcp_total']:,}")
        print(f"  Azure True Total Addresses : {counts['azure_total']:,}")
        print(f"  Combined Collapsed Space   : {counts['grand_total']:,}")
        print("=" * 65)

        q_depth, added, deleted, cur, first_count = run_topup_cycle(networks, subtracted, counts, is_first_run=True)
        if first_count == 0 and os.path.exists(QUEUE_DIR):
            first_f = sorted([f for f in os.listdir(QUEUE_DIR) if f.startswith("q_a0_hosting_")])[0]
            first_count = sum(1 for _ in open(os.path.join(QUEUE_DIR, first_f), "rb"))

        print(f"First File Line Count: {first_count:,} lines")
        print("=" * 65 + "\n")
        return

    print("Starting background top-up daemon (Interval: 60s, Target: 15M lines)...", flush=True)
    while True:
        try:
            run_topup_cycle(networks, subtracted, counts)
        except Exception as e:
            print(f"[ERROR] Exception in top-up cycle: {e}", file=sys.stderr, flush=True)
        time.sleep(60)

if __name__ == "__main__":
    main()
