"""
tools/benchmark_planted_load.py
Benchmarks the production probe under real scanning conditions against
the 100,000-IP dataset with 500 planted confirmed-live proxies.

Tests:
- 6 Workers
- 2 Workers
- 1 Worker

Measures:
- Planted Detection Count & Rate (% of 500)
- Scan Speed (IPs/s)
- Real Discovery Yield (genuine proxies found in real 99.5k portion)
- Socket Error Breakdown (errno99/WSAEADDRINUSE, timeouts, refused)
"""
import argparse
import asyncio
import json
import multiprocessing
import os
import socket
import ssl
import sys
import time

ROOT = r"D:\DEpinFarm"
IPS_PATH = os.path.join(ROOT, "ip", "harvest", "benchmark_100k_planted.txt")
GT_PATH = os.path.join(ROOT, "ip", "harvest", "benchmark_ground_truth.json")
RESULTS_PATH = os.path.join(ROOT, "ip", "harvest", "benchmark_results.json")

DIRECT_PORTS = [443, 3128, 8080, 80, 8888]
TARGETS = ["speed.cloudflare.com", "www.google.com", "one.one.one.one"]

# Pre-build TLS ClientHellos
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
        try: s.close()
        except Exception: pass

async def probe_single_target(ip, port, target, timeout=5.0):
    loop = asyncio.get_running_loop()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setblocking(False)
    try:
        await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=timeout)
        return await inline_probe_connected(s, target, timeout=timeout)
    except Exception:
        try: s.close()
        except Exception: pass
        return False

def worker_main(worker_id, num_workers, ip_subset, planted_ips_set, return_dict):
    async def run_worker_async():
        DIRECT_SEM = asyncio.Semaphore(2500)
        BATCH_SIZE = 1500

        stat_timeout = 0
        stat_refused = 0
        stat_errno99 = 0
        stat_other = 0

        detected_planted = []
        discovered_real = []

        async def check_port(ip, port):
            nonlocal stat_timeout, stat_refused, stat_errno99, stat_other
            async with DIRECT_SEM:
                loop = asyncio.get_running_loop()
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setblocking(False)
                try:
                    await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=1.8)
                except asyncio.TimeoutError:
                    stat_timeout += 1
                    try: s.close()
                    except Exception: pass
                    return None
                except ConnectionRefusedError:
                    stat_refused += 1
                    try: s.close()
                    except Exception: pass
                    return None
                except OSError as e:
                    err_no = getattr(e, "errno", None)
                    win_err = getattr(e, "winerror", None)
                    msg = str(e).lower()
                    if err_no in (99, 10048, 10055) or win_err in (10048, 10055) or "cannot assign" in msg or "only one usage" in msg:
                        stat_errno99 += 1
                    else:
                        stat_other += 1
                    try: s.close()
                    except Exception: pass
                    return None
                except Exception:
                    stat_other += 1
                    try: s.close()
                    except Exception: pass
                    return None

                # TLS multi-target handshake
                if await inline_probe_connected(s, "speed.cloudflare.com", timeout=5.0):
                    return port, "speed.cloudflare.com"

                for t in ["www.google.com", "one.one.one.one"]:
                    if await probe_single_target(ip, port, t, timeout=5.0):
                        return port, t
                return None

        total_ips = len(ip_subset)
        offset = 0
        last_log_t = time.time()
        start_worker_t = time.time()

        while offset < total_ips:
            batch = ip_subset[offset : offset + BATCH_SIZE]
            tasks = []
            for ip in batch:
                for p in DIRECT_PORTS:
                    tasks.append((ip, p, check_port(ip, p)))

            results = await asyncio.gather(*[t[2] for t in tasks], return_exceptions=True)

            for (ip, port, _), res in zip(tasks, results):
                if isinstance(res, tuple) and res[0] is not None:
                    p_found, target = res
                    cand_str = f"{ip}:{p_found}"
                    if ip in planted_ips_set:
                        detected_planted.append((ip, p_found, target))
                    else:
                        discovered_real.append((ip, p_found, target))

            offset += len(batch)
            now = time.time()
            if worker_id == 0 and (now - last_log_t >= 10 or offset >= total_ips):
                last_log_t = now
                dt = max(0.1, now - start_worker_t)
                prog_pct = (offset / total_ips) * 100.0
                speed = (offset * num_workers) / dt
                print(f"[{num_workers}W Progress] Scanned ~{offset * num_workers:,}/{total_ips * num_workers:,} IPs ({prog_pct:.1f}%) | Speed: {speed:.1f} IPs/s | Planted found (W0): {len(detected_planted)}", flush=True)

        return {
            "worker_id": worker_id,
            "scanned": total_ips,
            "detected_planted": detected_planted,
            "discovered_real": discovered_real,
            "timeout": stat_timeout,
            "refused": stat_refused,
            "errno99": stat_errno99,
            "other": stat_other,
        }

    res = asyncio.run(run_worker_async())
    return_dict[worker_id] = res

def run_suite_for_workers(num_workers, all_ips, ground_truth):
    planted_dict = ground_truth["planted_proxies"]
    planted_set = set(planted_dict.keys())
    total_planted_in_sample = sum(1 for ip in all_ips if ip in planted_set)

    print("\n" + "=" * 70, flush=True)
    print(f"BENCHMARK RUN: {num_workers} WORKER{'S' if num_workers > 1 else ''}", flush=True)
    print(f"Total IPs: {len(all_ips):,} | Planted Proxies in stream: {total_planted_in_sample}", flush=True)
    print("=" * 70, flush=True)

    manager = multiprocessing.Manager()
    return_dict = manager.dict()

    workers = []
    t0 = time.time()

    for w in range(num_workers):
        subset = all_ips[w::num_workers]
        p = multiprocessing.Process(
            target=worker_main,
            args=(w, num_workers, subset, planted_set, return_dict)
        )
        workers.append(p)
        p.start()

    for p in workers:
        p.join()

    elapsed = time.time() - t0

    # Aggregate worker results
    all_detected_planted = []
    all_discovered_real = []
    total_scanned = 0
    total_timeout = 0
    total_refused = 0
    total_errno99 = 0
    total_other = 0

    for w in range(num_workers):
        w_res = return_dict[w]
        total_scanned += w_res["scanned"]
        all_detected_planted.extend(w_res["detected_planted"])
        all_discovered_real.extend(w_res["discovered_real"])
        total_timeout += w_res["timeout"]
        total_refused += w_res["refused"]
        total_errno99 += w_res["errno99"]
        total_other += w_res["other"]

    # Unique detected planted
    detected_planted_ips = set(ip for ip, p, tgt in all_detected_planted)
    planted_detected_count = len(detected_planted_ips)
    planted_detection_rate = (planted_detected_count / max(1, total_planted_in_sample)) * 100.0

    # Real portion metrics
    real_sample_size = len(all_ips) - total_planted_in_sample
    unique_real_discovered = set(ip for ip, p, tgt in all_discovered_real)
    real_yield_per_100k = (len(unique_real_discovered) / max(1, real_sample_size)) * 100000.0 if real_sample_size > 0 else 0.0

    ips_per_sec = total_scanned / max(0.001, elapsed)

    print(f"\n--- RESULTS FOR {num_workers} WORKER{'S' if num_workers > 1 else ''} ---", flush=True)
    print(f"Elapsed Time           : {elapsed:.2f} s ({elapsed/60:.2f} min)", flush=True)
    print(f"IP Scan Throughput     : {ips_per_sec:.1f} IPs/s", flush=True)
    print(f"Planted Proxies Tested : {total_planted_in_sample}", flush=True)
    print(f"Planted Detected       : {planted_detected_count} / {total_planted_in_sample} ({planted_detection_rate:.2f}%)", flush=True)
    print(f"Real Portion Discovered: {len(unique_real_discovered)} genuine proxies ({real_yield_per_100k:.2f} per 100k)", flush=True)
    print(f"Socket Stats           : timeout={total_timeout:,} | refused={total_refused:,} | errno99={total_errno99:,} | other={total_other:,}", flush=True)

    return {
        "workers": num_workers,
        "elapsed_sec": round(elapsed, 2),
        "ips_per_sec": round(ips_per_sec, 1),
        "total_scanned": total_scanned,
        "planted_tested": total_planted_in_sample,
        "planted_detected": planted_detected_count,
        "planted_detection_rate_pct": round(planted_detection_rate, 2),
        "real_tested": real_sample_size,
        "real_discovered": len(unique_real_discovered),
        "real_yield_per_100k": round(real_yield_per_100k, 2),
        "stat_timeout": total_timeout,
        "stat_refused": total_refused,
        "stat_errno99": total_errno99,
        "stat_other": total_other,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, nargs="+", default=[6, 2, 1], help="Worker counts to benchmark")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit for fast smoke testing")
    args = parser.parse_args()

    print("=" * 70, flush=True)
    print("PRODUCTION PROBE BENCHMARK UNDER REAL SOCKET PRESSURE", flush=True)
    print("=" * 70, flush=True)

    with open(GT_PATH, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    with open(IPS_PATH, "r", encoding="utf-8") as f:
        all_ips = [line.strip() for line in f if line.strip()]

    if args.limit > 0:
        all_ips = all_ips[:args.limit]
        print(f"Smoke test limit active: {len(all_ips)} IPs")

    all_results = []
    for w in args.workers:
        res = run_suite_for_workers(w, all_ips, ground_truth)
        all_results.append(res)
        # Brief pause between runs to let sockets completely drain
        time.sleep(3)

    print("\n" + "=" * 80, flush=True)
    print("FINAL BENCHMARK COMPARISON MATRIX")
    print("=" * 80, flush=True)
    header = f"{'Workers':<8} {'Planted Detected':<18} {'Catch Rate':<12} {'Scan Speed':<14} {'Real Found':<12} {'Real /100k':<12}"
    print(header, flush=True)
    print("-" * 80, flush=True)
    for r in all_results:
        det_str = f"{r['planted_detected']}/{r['planted_tested']}"
        rate_str = f"{r['planted_detection_rate_pct']}%"
        spd_str = f"{r['ips_per_sec']} IP/s"
        row = f"{r['workers']:<8} {det_str:<18} {rate_str:<12} {spd_str:<14} {r['real_discovered']:<12} {r['real_yield_per_100k']:<12}"
        print(row, flush=True)
    print("=" * 80, flush=True)

    if args.limit == 0:
        with open(RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2)
        print(f"\nSaved benchmark results to {RESULTS_PATH}")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
