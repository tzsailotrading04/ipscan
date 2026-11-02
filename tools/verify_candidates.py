import os
import sys
import ssl
import time
import socket
import argparse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

TARGETS = ["blnc.traffmonetizer.com", "88.99.65.143"]
SSL_CTX = ssl.create_default_context()

def hs(sock, target, timeout=8.0):
    try:
        sock.setblocking(True)
        sock.settimeout(timeout)
        sock.sendall(f"CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\n\r\n".encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            ch = sock.recv(512)
            if not ch:
                return False
            resp += ch
            if len(resp) > 2048:
                return False
        first = resp.split(b"\r\n")[0]
        if not (b" 200" in first or b"HTTP/1.1 200" in first or b"HTTP/1.0 200" in first):
            return False
        ss = SSL_CTX.wrap_socket(sock, server_hostname="blnc.traffmonetizer.com")
        ss.settimeout(timeout)
        ss.do_handshake()
        c = ss.getpeercert()
        ss.close()
        return bool(c)
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
        return False

def check_targets_once(ip, port, timeout=8.0):
    t0 = time.time()
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
        if hs(s, TARGETS[0], timeout):
            lat_ms = int((time.time() - t0) * 1000)
            return True, TARGETS[0], lat_ms
    except Exception:
        pass

    for t in TARGETS[1:]:
        t0_t = time.time()
        try:
            s2 = socket.create_connection((ip, port), timeout=timeout)
            if hs(s2, t, timeout):
                lat_ms = int((time.time() - t0_t) * 1000)
                return True, t, lat_ms
        except Exception:
            pass
    return False, None, 0

def one(ip, port, timeout=8.0):
    # Attempt 1
    good, tgt, lat_ms = check_targets_once(ip, port, timeout)
    if good and lat_ms <= 1500:
        return ip, port, True, tgt, lat_ms

    # Retry with 2-second delay
    time.sleep(2.0)
    good, tgt, lat_ms = check_targets_once(ip, port, timeout)
    if good and lat_ms <= 1500:
        return ip, port, True, tgt, lat_ms

    return ip, port, False, None, lat_ms

def parse_ts(ts_str):
    ts_str = ts_str.strip().strip("[]")
    if not ts_str:
        return 0.0
    try:
        return float(ts_str)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(ts_str, fmt).replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            pass
    return 0.0

def load_and_decay_suspects(filepath, max_age_sec=6 * 3600):
    now_ts = datetime.now(timezone.utc).timestamp()
    suspects = {}
    decayed = 0
    if not os.path.exists(filepath):
        return suspects, decayed

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                ep = parts[0].strip()
                ts_val = parse_ts(parts[1])
            else:
                parts_sp = line.split()
                ep = parts_sp[0].strip()
                ts_val = parse_ts(parts_sp[1]) if len(parts_sp) > 1 else 0.0

            if ":" in ep:
                if (now_ts - ts_val) > max_age_sec:
                    decayed += 1
                else:
                    suspects[ep] = ts_val

    # Rewrite cleaned suspects without expired entries
    save_suspects(filepath, suspects)
    return suspects, decayed

def save_suspects(filepath, suspects):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    tmp_path = filepath + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        for ep, ts in suspects.items():
            iso_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            f.write(f"{ep}\t{iso_str}\n")
    if os.path.exists(tmp_path):
        os.replace(tmp_path, filepath)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--pool", default="ip/harvest/real_pool.txt")
    ap.add_argument("--out-alive", default="ip/harvest/verified_alive_part_local.txt")
    ap.add_argument("--out-dead", default="cache/pool_dead.txt")
    ap.add_argument("--suspect", default="cache/pool_suspect.txt")
    ap.add_argument("--workers", type=int, default=200)
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()

    # 1. Six-hour decay on startup
    suspects, decayed = load_and_decay_suspects(a.suspect, max_age_sec=6 * 3600)

    # Load candidates
    cands = []
    seen = set()
    with open(a.input, encoding="utf-8", errors="ignore") as f:
        for l in f:
            ep = l.strip().split("\t")[0].split()[0] if l.strip() else ""
            if not ep or ep in seen:
                continue
            p = ep.split(":")
            if len(p) == 2 and p[1].isdigit():
                cands.append((p[0], int(p[1])))
                seen.add(ep)
                if a.limit and len(cands) >= a.limit:
                    break

    print("to verify:", len(cands))
    if not cands:
        print(f"verified=0, first_strike=0, confirmed_dead=0, decayed={decayed}, fast_tagged=0")
        return

    os.makedirs(os.path.dirname(a.out_alive), exist_ok=True)
    os.makedirs(os.path.dirname(a.out_dead), exist_ok=True)

    verified = 0
    fast_tagged = 0
    first_strike = 0
    confirmed_dead = 0
    dead_dropped = set()
    latencies = []

    t0 = time.time()
    now_utc = datetime.now(timezone.utc)
    now_ts = now_utc.timestamp()
    now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(one, ip, pt, a.timeout) for ip, pt in cands]
        for fu in as_completed(futs):
            ip, pt, good, tgt, lat_ms = fu.result()
            ep = f"{ip}:{pt}"
            if good:
                verified += 1
                latencies.append(lat_ms)
                is_fast = (lat_ms <= 300)
                if is_fast:
                    fast_tagged += 1
                tag = "fast" if is_fast else "normal"
                with open(a.out_alive, "a", encoding="utf-8") as af:
                    af.write(f"{ep}\t{tgt}\tLOCAL\t{lat_ms}\t{tag}\n")
                # If it had a strike previously, successful verify clears it
                if ep in suspects:
                    del suspects[ep]
            else:
                # Two-strike rule
                if ep not in suspects:
                    # Strike 1: NOT in pool_suspect.txt
                    first_strike += 1
                    suspects[ep] = now_ts
                else:
                    earlier_ts = suspects[ep]
                    age_sec = now_ts - earlier_ts
                    if age_sec < 3600:
                        # Strike 2: earlier strike < 60 minutes old -> confirmed dead
                        confirmed_dead += 1
                        del suspects[ep]
                        dead_dropped.add(ep)
                        with open(a.out_dead, "a", encoding="utf-8") as df:
                            df.write(f"[{now_iso}] {ep}\tspeed.cloudflare.com\tLOCAL\tREASON:FAIL_CONNECT\tRETIRED\n")
                    else:
                        # Earlier strike is 60+ minutes old -> treat as fresh first strike
                        first_strike += 1
                        suspects[ep] = now_ts

    # Save updated suspect pool
    save_suspects(a.suspect, suspects)

    # Drop confirmed dead from working pool if present
    if dead_dropped and os.path.exists(a.pool):
        with open(a.pool, "r", encoding="utf-8", errors="ignore") as pf:
            pool_lines = pf.readlines()
        with open(a.pool, "w", encoding="utf-8") as pf:
            for pl in pool_lines:
                ep_l = pl.strip().split("\t")[0].split()[0] if pl.strip() else ""
                if ep_l not in dead_dropped:
                    pf.write(pl)

    # Print required one-line summary and average latency
    avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
    print(f"verified={verified}, first_strike={first_strike}, confirmed_dead={confirmed_dead}, decayed={decayed}, fast_tagged={fast_tagged}")
    print(f"average_latency={avg_lat:.1f}ms")

if __name__ == "__main__":
    main()
