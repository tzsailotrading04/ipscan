import os
import csv
import json
import time
import urllib.request
import urllib.error

ROOT = r"D:\DEpinFarm"
CLASSIFIED_TSV = os.path.join(ROOT, "master_pool_classified.tsv")
CACHE_FILE = os.path.join(ROOT, "data", "peeringdb_cache.tsv")

# Step 1: Enumerate every distinct ASN present in master_pool_classified.tsv
asns = []
seen = set()
with open(CLASSIFIED_TSV, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f, delimiter="\t")
    for row in reader:
        asn = row.get("asn", "").strip()
        if asn and asn not in seen:
            seen.add(asn)
            asns.append(asn)

print(f"Total distinct ASNs in master_pool_classified.tsv: {len(asns)}")

# Fetch all PeeringDB nets using limit=0 with backoff
url = "https://www.peeringdb.com/api/net?fields=asn,name,name_long,info_type&limit=0"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DEpinFarm-Validator/1.0"
}

pdb_data = None
for attempt in range(5):
    try:
        print(f"Requesting full PeeringDB net table (attempt {attempt+1})...", flush=True)
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            pdb_data = data.get("data", [])
            print(f"Successfully received {len(pdb_data)} PeeringDB networks.")
            break
    except urllib.error.HTTPError as e:
        retry_after = 5
        try:
            if "Retry-After" in e.headers:
                retry_after = int(e.headers["Retry-After"]) + 1
        except Exception:
            pass
        print(f"HTTPError {e.code}: {e.reason}. Sleeping {retry_after}s before retry...", flush=True)
        time.sleep(retry_after)
    except Exception as e:
        print(f"Error: {e}. Sleeping 5s before retry...", flush=True)
        time.sleep(5)

if pdb_data is None:
    raise RuntimeError("Failed to fetch PeeringDB data after 5 attempts.")

pdb_map = {}
for item in pdb_data:
    item_asn = str(item.get("asn", "")).strip()
    if item_asn and item_asn != "0":
        # Keep non-empty info_type if duplicate
        it = item.get("info_type") or "Not Disclosed"
        if item_asn not in pdb_map or (it != "Not Disclosed" and pdb_map[item_asn]["info_type"] == "Not Disclosed"):
            pdb_map[item_asn] = {
                "info_type": it,
                "name": item.get("name") or "",
                "name_long": item.get("name_long") or ""
            }

# Build cache for all ASNs
cache = {}
found_count = 0
not_found_count = 0

for a in asns:
    if a in pdb_map:
        cache[a] = pdb_map[a]
        found_count += 1
    else:
        cache[a] = {
            "info_type": "404",
            "name": "",
            "name_long": ""
        }
        not_found_count += 1

print(f"Matched {found_count} ASNs in PeeringDB, {not_found_count} marked 404.")

# Save to data/peeringdb_cache.tsv
os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
with open(CACHE_FILE, "w", encoding="utf-8", newline="\n") as f:
    writer = csv.DictWriter(f, fieldnames=["asn", "info_type", "name", "name_long"], delimiter="\t")
    writer.writeheader()
    for a in sorted(cache.keys(), key=lambda x: int(x) if x.isdigit() else 9999999):
        writer.writerow({
            "asn": a,
            "info_type": cache[a]["info_type"],
            "name": cache[a]["name"],
            "name_long": cache[a]["name_long"]
        })

print(f"Saved {len(cache)} ASN records to {CACHE_FILE}")
