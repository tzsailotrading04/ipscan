import os, subprocess, sys, time

REPO = r"D:\DEpinFarm"
H = os.path.join(REPO, "ip", "harvest")
WINDOW = int(sys.argv[1]) if len(sys.argv) > 1 else 600
KEYS = ["ok", "not_found", "rate_limit", "timeout", "other", "ok_with_ports", "ok_no_keep", "kept_lines"]

def pull():
    subprocess.run(["git", "-C", REPO, "pull", "--rebase", "--autostash", "origin", "main"],
                   capture_output=True)

def read_stats():
    agg = {k: 0 for k in KEYS}
    engines = set()
    for i in range(20):
        p = os.path.join(H, f"shodan_stats_v98_{i:02d}.txt")
        if not os.path.exists(p):
            continue
        for l in open(p, encoding="utf-8", errors="ignore"):
            if "=" not in l:
                continue
            k, v = l.strip().split("=", 1)
            if k == "engine":
                engines.add(v)
            elif k in agg and v.isdigit():
                agg[k] += int(v)
    return agg, engines

def read_prog():
    o = {}
    for i in range(20):
        p = os.path.join(H, f"shodan_progress_v98_{i:02d}.txt")
        vals = []
        try:
            for l in open(p, errors="ignore"):
                t = l.strip()
                if t.isdigit():
                    vals.append(int(t))
        except Exception:
            pass
        o[i] = max(vals) if vals else 0
    return o

def read_cands():
    o = {}
    for i in range(20):
        p = os.path.join(H, f"shodan_shard_v98_{i:02d}.txt")
        try:
            o[i] = sum(1 for _ in open(p, encoding="utf-8", errors="ignore"))
        except Exception:
            o[i] = 0
    return o

pull()
s0, eng0 = read_stats()
p0, c0 = read_prog(), read_cands()
print(f"engines seen: {sorted(eng0) or ['NONE']}")
print(f"waiting {WINDOW}s...", flush=True)
t0 = time.time()
time.sleep(WINDOW)
pull()
s1, eng1 = read_stats()
p1, c1 = read_prog(), read_cands()
el = time.time() - t0

print("=" * 70)
print(f"{'Shard':8}{'DeltaQ':>10}{'Req/s':>9}{'DltCands':>11}{'ok':>9}{'404':>9}")
print("-" * 70)
tq = tc = 0
for i in range(20):
    dq = max(0, p1[i] - p0[i]); dc = max(0, c1[i] - c0[i])
    tq += dq; tc += dc
    print(f"Shard {i:02d}{dq:>10,}{dq/max(1,el):>9.1f}{dc:>11,}"
          f"{s1['ok']-s0['ok'] if False else 0:>9}{0:>9}")
print("-" * 70)
d = {k: s1[k] - s0[k] for k in KEYS}
fleet = tq / max(1, el)
print(f"FLEET RATE:      {fleet:,.1f} req/s")
print(f"DELTA QUERIES:   {tq:,}")
print(f"DELTA CAND LINES:{tc:,}   ({(tc/tq*100) if tq else 0:.3f}%)")
print(f"STATUS DELTAS:   " + "  ".join(f"{k}={d[k]}" for k in KEYS))
print(f"ENGINES:         {sorted(eng1) or ['NONE']}")
print("=" * 70)

if eng1 and all(e != "v98.2" for e in eng1):
    print("DIAGNOSIS: WRONG CODE RUNNING - no v98.2 engine reported")
elif d["ok"] == 0 and d["not_found"] > 0:
    print("DIAGNOSIS: IP SPACE EMPTY - subnet list or offset mapping is wrong")
elif d["ok"] > 0 and d["kept_lines"] == 0 and d["ok_no_keep"] > 0:
    print("DIAGNOSIS: PORT FILTER TOO STRICT - InternetDB returns ports but none match pe_ports")
elif d["rate_limit"] > tq * 0.05:
    print("DIAGNOSIS: THROTTLED - lower TARGET_RATE to 80")
elif d["kept_lines"] > 0:
    print("DIAGNOSIS: WORKING")
else:
    print("DIAGNOSIS: INCONCLUSIVE - report the status deltas")

