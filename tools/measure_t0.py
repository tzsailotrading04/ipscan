import subprocess
import datetime
import json
import os

utc_now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()

print("=== T0 MEASUREMENT ===")
print("UTC Time:", utc_now)
print()
hdr = f"{'Shard':<6} | {'Scanned':<12} | {'Genuine (since restart)':<24} | {'Source'}"
print(hdr)
print("-" * 75)

shards_data = {}
for i in range(20):
    tag = f"{i:02d}"
    ref = f"origin/out/sh{tag}:work/sh{tag}_stats.txt"
    res = subprocess.run(["git", "show", ref], capture_output=True, text=True)
    raw = res.stdout.strip()
    parts = raw.split()
    scanned = 0
    genuine = 0
    source = "work"
    if res.returncode == 0 and len(parts) >= 3 and parts[1].isdigit():
        scanned = int(parts[1])
        genuine = int(parts[2])
    else:
        ref2 = f"origin/out/sh{tag}:ip/harvest/shodan_stats_v98_{tag}.txt"
        res2 = subprocess.run(["git", "show", ref2], capture_output=True, text=True)
        if res2.returncode == 0:
            kv = dict(l.split("=", 1) for l in res2.stdout.splitlines() if "=" in l)
            scanned = int(kv.get("offset", 0))
            genuine = int(kv.get("cands", 0))
            source = "ip/harvest"
    
    shards_data[f"sh{tag}"] = {
        "scanned": scanned,
        "genuine": genuine,
        "source": source
    }
    print(f"sh{tag:<4} | {scanned:<12} | {genuine:<24} | {source}")

t0_obj = {
    "t0_utc": utc_now,
    "t0_ts": now_ts,
    "shards": shards_data
}
os.makedirs("work", exist_ok=True)
with open("work/fleet_10m_t0.json", "w") as f:
    json.dump(t0_obj, f, indent=2)
print("-" * 75)
print("Saved T0 baseline to work/fleet_10m_t0.json")
