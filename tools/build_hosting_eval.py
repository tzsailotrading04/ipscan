import os
import sys
import gzip
import base64
import json

REPO_ROOT = r"D:\DEpinFarm"
HOSTING_FILE = os.path.join(REPO_ROOT, "kaggle", "test_hosting_eval", "hosting_20k.txt")
GROUNDTRUTH_FILE = os.path.join(REPO_ROOT, "work", "groundtruth.txt")
OUT_DIR = os.path.join(REPO_ROOT, "kaggle", "test_hosting_eval")
OUT_RUN_PY = os.path.join(OUT_DIR, "run.py")
OUT_META_JSON = os.path.join(OUT_DIR, "kernel-metadata.json")

def main():
    with open(HOSTING_FILE, "rb") as f:
        raw_20k = f.read()

    comp_20k = base64.b64encode(gzip.compress(raw_20k)).decode("ascii")

    with open(GROUNDTRUTH_FILE, "r", encoding="utf-8") as f:
        gt_lines = [l.strip() for l in f if l.strip()]

    meta = {
        "id": "spectatorlone/test-hosting-eval-20k",
        "title": "test-hosting-eval-20k",
        "code_file": "run.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": False,
        "enable_internet": True,
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": []
    }
    with open(OUT_META_JSON, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    code = f'''#!/usr/bin/env python3
import os
import sys
import time
import gzip
import base64
import socket
import ssl
import asyncio
import subprocess
import concurrent.futures

# System resource limits for high concurrency
try:
    import resource
    resource.setrlimit(resource.RLIMIT_NOFILE, (65535, 65535))
except Exception:
    pass

try:
    subprocess.run(["sysctl", "-w", "net.ipv4.ip_local_port_range=10000 65535"], capture_output=True, check=False)
    subprocess.run(["sysctl", "-w", "net.ipv4.tcp_tw_reuse=1"], capture_output=True, check=False)
except Exception:
    pass

DIRECT_PORTS = [443, 3128, 8080, 8888, 1080, 8118, 80, 4145]
TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]
SSL_CTX = ssl.create_default_context()

GROUNDTRUTH_PROXIES = {repr(gt_lines)}

RAW_20K_B64 = """{comp_20k}"""

def sync_tls_handshake(sock, target, timeout=5.0):
    try:
        sock.setblocking(True)
        sock.settimeout(timeout)
        req = f"CONNECT {{target}}:443 HTTP/1.1\\r\\nHost: {{target}}:443\\r\\n\\r\\n".encode()
        sock.sendall(req)
        resp = b""
        while b"\\r\\n\\r\\n" not in resp:
            chunk = sock.recv(512)
            if not chunk: return False
            resp += chunk
            if len(resp) > 2048: return False
        first_line = resp.split(b"\\r\\n")[0]
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
        return False
    finally:
        try: sock.close()
        except Exception: pass

def sync_probe_target(ip, port, target, timeout=5.0):
    s = None
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
        return sync_tls_handshake(s, target, timeout=timeout)
    except Exception:
        if s:
            try: s.close()
            except Exception: pass
        return False

async def check_port(ip, port, sem, loop):
    async with sem:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(False)
        try:
            await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=5.0)
        except Exception:
            try: s.close()
            except Exception: pass
            return None

        # Primary target probe with connected socket
        if await loop.run_in_executor(None, sync_tls_handshake, s, "speed.cloudflare.com", 5.0):
            return port, "speed.cloudflare.com"

        for t in ["www.google.com", "one.one.one.one"]:
            if await loop.run_in_executor(None, sync_probe_target, ip, port, t, 5.0):
                return port, t
        return None

async def run_groundtruth_control(sem, loop):
    print("=" * 75, flush=True)
    print(f"RUNNING GROUNDTRUTH CONTROL: {{len(GROUNDTRUTH_PROXIES)}} PROXIES (Concurrency: 200, Timeout: 5.0s)", flush=True)
    print("=" * 75, flush=True)
    t0 = time.time()
    tasks = []
    for item in GROUNDTRUTH_PROXIES:
        parts = item.split(":")
        ip = parts[0]
        port = int(parts[1])
        tasks.append((ip, port, check_port(ip, port, sem, loop)))

    results = await asyncio.gather(*[t[2] for t in tasks], return_exceptions=True)
    passed_items = []
    for (ip, port, _), res in zip(tasks, results):
        if isinstance(res, tuple) and res[0] is not None:
            passed_items.append((ip, port, res[1]))

    dur = time.time() - t0
    total = len(GROUNDTRUTH_PROXIES)
    passed_cnt = len(passed_items)
    pct = (passed_cnt / total) * 100.0 if total else 0.0
    print(f"Groundtruth Control Finished in {{dur:.2f}}s", flush=True)
    print(f"Total Tested : {{total}}", flush=True)
    print(f"Passed       : {{passed_cnt}} / {{total}} ({{pct:.2f}}%)", flush=True)
    print("=" * 75, flush=True)
    return {{
        "total": total,
        "passed": passed_cnt,
        "pct": pct,
        "duration": dur,
        "passed_items": passed_items
    }}

async def run_hosting_eval(sem, loop, hosting_ips, chunk_size=500):
    total_ips = len(hosting_ips)
    print("=" * 75, flush=True)
    print(f"RUNNING HOSTING EVALUATION: {{total_ips}} ADDRESSES (Concurrency: 200, Timeout: 5.0s)", flush=True)
    print(f"Ports per address: {{DIRECT_PORTS}} (Total probes: {{total_ips * len(DIRECT_PORTS)}})", flush=True)
    print("=" * 75, flush=True)
    
    t0 = time.time()
    passed_addresses = set()
    passed_ports = []
    probes_completed = 0
    ips_completed = 0

    num_chunks = (total_ips + chunk_size - 1) // chunk_size

    for c_idx in range(num_chunks):
        chunk_ips = hosting_ips[c_idx * chunk_size : (c_idx + 1) * chunk_size]
        chunk_tasks = []
        for ip in chunk_ips:
            for p in DIRECT_PORTS:
                chunk_tasks.append((ip, p, check_port(ip, p, sem, loop)))

        results = await asyncio.gather(*[t[2] for t in chunk_tasks], return_exceptions=True)
        
        for (ip, port, _), res in zip(chunk_tasks, results):
            if isinstance(res, tuple) and res[0] is not None:
                passed_addresses.add(ip)
                passed_ports.append((ip, port, res[1]))
                print(f"[FOUND HOSTING PROXY] {{ip}}:{{port}} via {{res[1]}} | Total Passed IPs: {{len(passed_addresses)}}", flush=True)

        probes_completed += len(chunk_tasks)
        ips_completed += len(chunk_ips)
        elapsed = time.time() - t0
        rate_ips = ips_completed / elapsed if elapsed > 0 else 0
        rate_probes = probes_completed / elapsed if elapsed > 0 else 0
        pct_done = (ips_completed / total_ips) * 100.0

        print(f"[PROGRESS {{c_idx + 1}}/{{num_chunks}}] {{ips_completed}}/{{total_ips}} IPs ({{pct_done:.1f}}%) | Probes: {{probes_completed}} | Passed IPs: {{len(passed_addresses)}} | Elapsed: {{elapsed:.1f}}s | Rate: {{rate_probes:.1f}} probes/s ({{rate_ips:.1f}} ips/s)", flush=True)

    dur = time.time() - t0
    passed_cnt = len(passed_addresses)
    pct = (passed_cnt / total_ips) * 100.0 if total_ips else 0.0

    print("=" * 75, flush=True)
    print(f"Hosting Evaluation Finished in {{dur:.2f}}s", flush=True)
    print(f"Total Addresses Tested : {{total_ips}}", flush=True)
    print(f"Passed Addresses       : {{passed_cnt}} / {{total_ips}} ({{pct:.2f}}%)", flush=True)
    print(f"Total Working Ports    : {{len(passed_ports)}}", flush=True)
    print("=" * 75, flush=True)

    return {{
        "total_addresses": total_ips,
        "passed_addresses": passed_cnt,
        "pct": pct,
        "passed_ports_cnt": len(passed_ports),
        "duration": dur,
        "passed_addresses_list": list(passed_addresses),
        "passed_ports": passed_ports
    }}

async def main_async():
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=250)
    loop = asyncio.get_running_loop()
    loop.set_default_executor(executor)
    sem = asyncio.Semaphore(200)

    # Decompress 20k hosting IPs
    raw_bytes = gzip.decompress(base64.b64decode(RAW_20K_B64))
    hosting_ips = [line.strip() for line in raw_bytes.decode('utf-8').splitlines() if line.strip()]

    print(f"Loaded {{len(GROUNDTRUTH_PROXIES)}} Groundtruth proxies and {{len(hosting_ips)}} Hosting addresses.", flush=True)

    # 1. Run Groundtruth Control
    gt_res = await run_groundtruth_control(sem, loop)

    # 2. Run Hosting Evaluation
    host_res = await run_hosting_eval(sem, loop, hosting_ips, chunk_size=500)

    # 3. Print Side-by-Side Comparison
    print("\\n" + "#" * 80, flush=True)
    print("# FINAL SIDE-BY-SIDE PROBE EVALUATION RESULTS", flush=True)
    print("#" * 80, flush=True)
    print(f"{{'Metric':<30}} | {{'Groundtruth Control':>20}} | {{'Hosting Queue (20k)':>20}}", flush=True)
    print("-" * 78, flush=True)
    print(f"{{'Input Total Tested':<30}} | {{gt_res['total']:>20,}} | {{host_res['total_addresses']:>20,}}", flush=True)
    print(f"{{'Pass Count':<30}} | {{gt_res['passed']:>20,}} | {{host_res['passed_addresses']:>20,}}", flush=True)
    print(f"{{'Pass Percentage':<30}} | {{gt_res['pct']:>19.2f}}% | {{host_res['pct']:>19.2f}}%", flush=True)
    scaled_gt = gt_res['pct'] * 200.0  # per 20,000
    print(f"{{'Pass Count (per 20,000)':<30}} | {{scaled_gt:>20.1f}} | {{host_res['passed_addresses']:>20,}}", flush=True)
    print(f"{{'Duration (seconds)':<30}} | {{gt_res['duration']:>19.1f}}s | {{host_res['duration']:>19.1f}}s", flush=True)
    print("#" * 80, flush=True)

    # Save summary json
    summary = {{
        "groundtruth": gt_res,
        "hosting": host_res
    }}
    with open("eval_results.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print("Results saved to eval_results.json", flush=True)

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
'''

    with open(OUT_RUN_PY, "w", encoding="utf-8") as f:
        f.write(code)

    print(f"Successfully generated {OUT_RUN_PY} ({len(code)} bytes) and {OUT_META_JSON}")

if __name__ == "__main__":
    main()
