import json
import urllib.request
import os

OUT = r"D:\DEpinFarm\data\hosting_asns.txt"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

KEEP = {"Network Services", "Content", "Enterprise", "NSP", "Cable/DSL/ISP", "Hosting"}

asns = set()
url = "https://www.peeringdb.com/api/net?fields=id,asn,info_type,name"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

print("Fetching PeeringDB networks...", flush=True)
try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        j = json.load(r)
    for net in j.get("data", []):
        t = net.get("info_type")
        a = net.get("asn")
        if a and t in KEEP:
            asns.add(int(a))
    print(f"PeeringDB returned {len(asns)} ASNs for types: {KEEP}", flush=True)
except Exception as e:
    print(f"PeeringDB API error: {e}", flush=True)

if not asns:
    print("Fallback to keyword filtering...", flush=True)
    src = r"D:\DEpinFarm\data\ip2asn-v4-u32.tsv"
    keywords = ["HOSTING", "CLOUD", "VPS", "SERVER", "DATACENTER", "DIGITAL", "HETZNER", "OVH", "LINODE", "LEASEWEB", "VULTR"]
    if os.path.exists(src):
        with open(src, errors="ignore") as f:
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) >= 5 and p[2].isdigit():
                    asn = int(p[2])
                    org = p[4].upper()
                    if any(k in org for k in keywords):
                        asns.add(asn)

with open(OUT, "w") as f:
    for a in sorted(asns):
        f.write(f"{a}\n")

print("HOSTING_ASNS", len(asns))
