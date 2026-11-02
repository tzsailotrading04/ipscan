import subprocess, json, datetime, time

with open("work/ten_min_comparison.json") as f:
    t0_data = json.load(f)

t0_ts = t0_data["t0_ts"]
now_ts = time.time()
dt = max(1.0, now_ts - t0_ts)
utc_now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

print("=== 10-MINUTE MEASUREMENT (T10) ===")
print("Current UTC Time:", utc_now)
print(f"Elapsed interval: {dt:.1f}s ({dt/60:.2f} min)")
print("-" * 105)
hdr = f"{'Shard':<6} | {'T0 Scanned':<12} | {'T10 Scanned':<12} | {'Delta Scan':<10} | {'Addr/sec':<9} | {'T0 Gen':<7} | {'T10 Gen':<8} | {'Delta Gen':<9} | {'Gen/1,000':<9}"
print(hdr)
print("-" * 105)

for sh in ["00", "01", "02", "03", "16"]:
    ref = f"origin/out/sh{sh}:work/sh{sh}_stats.txt"
    res = subprocess.run(["git", "show", ref], capture_output=True, text=True)
    raw = res.stdout.strip()
    parts = raw.split()
    scanned_10 = int(parts[1]) if len(parts) > 1 else 0
    gen_10 = int(parts[2]) if len(parts) > 2 else 0
    
    scanned_0 = t0_data["shards"][f"sh{sh}"]["scanned"]
    gen_0 = t0_data["shards"][f"sh{sh}"]["genuine"]
    
    d_scan = scanned_10 - scanned_0
    d_gen = gen_10 - gen_0
    
    rate_scan = d_scan / dt
    gen_per_1k = (d_gen / max(1, d_scan)) * 1000.0
    
    row = f"sh{sh:<4} | {scanned_0:<12} | {scanned_10:<12} | {d_scan:<10} | {rate_scan:<9.2f} | {gen_0:<7} | {gen_10:<8} | {d_gen:<9} | {gen_per_1k:<9.3f}"
    print(row)

print("-" * 105)
print("\nRaw T10 lines:")
for sh in ["00", "01", "02", "03", "16"]:
    ref = f"origin/out/sh{sh}:work/sh{sh}_stats.txt"
    res = subprocess.run(["git", "show", ref], capture_output=True, text=True)
    print(f"sh{sh}: {res.stdout.strip()}")
