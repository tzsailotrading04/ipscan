import json
import os
import sys

ROOT = r"D:\DEpinFarm"
ACCOUNTS = [
    ("acct5", "remruata", ["00", "01"]),
    ("acct1", "lalthazualasailo", ["02", "03", "04", "05"]),
    ("acct2", "zomuanpuia", ["06", "07", "08", "09"]),
    ("acct3", "laldinthari", ["10", "11", "12", "13"]),
    ("acct6", "spectatorlone", ["14", "18", "19"]),
    ("acct4", "lalsangkima", ["15", "16", "17"]),
]

print("Checking metadata files...")
for acct, user, shards in ACCOUNTS:
    for s in shards:
        meta_p = os.path.join(ROOT, "kaggle", f"cl_shodan_{s}", "kernel-metadata.json")
        with open(meta_p, "r", encoding="utf-8") as f:
            data = json.load(f)
        kid = data.get("id", "")
        expected = f"{user}/ipscan-cl-shodan-{s}"
        if kid != expected:
            print(f"MISMATCH in {s}: id='{kid}', updating to '{expected}'")
            data["id"] = expected
            with open(meta_p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        else:
            print(f"OK: shard {s} -> {kid}")

# Also check cl_harvest
harvest_meta_p = os.path.join(ROOT, "kaggle", "cl_harvest", "kernel-metadata.json")
with open(harvest_meta_p, "r", encoding="utf-8") as f:
    hdata = json.load(f)
hkid = hdata.get("id", "")
hexpected = "remruata/ipscan-cl-harvest"
if hkid != hexpected:
    print(f"MISMATCH in cl_harvest: id='{hkid}', updating to '{hexpected}'")
    hdata["id"] = hexpected
    with open(harvest_meta_p, "w", encoding="utf-8") as f:
        json.dump(hdata, f, indent=2)
else:
    print(f"OK: cl_harvest -> {hkid}")
