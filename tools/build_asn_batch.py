import os, random, ipaddress, collections

TSV = "data/ip2asn-v4-u32.tsv"
POOL = "ip/harvest/real_pool.txt"
OUTDIR = "ip/harvest/queue"
ADDRS = 15000
PORTS = (8080, 3128, 8888, 1080, 81, 8000, 999, 8118)
CHUNK = 40000
STAMP = "1793435000"
TOPN = 60

org2asn = {}
ranges = collections.defaultdict(list)
with open(TSV, encoding="utf-8", errors="ignore") as f:
    for line in f:
        p = line.rstrip("\n").split("\t")
        if len(p) < 5:
            continue
        try:
            s, e, a = int(p[0]), int(p[1]), int(p[2])
        except Exception:
            continue
        if a == 0 or e < s:
            continue
        org = p[4].strip().upper()
        org2asn.setdefault(org, a)
        ranges[a].append((s, e))

cnt = collections.Counter()
pool = set()
with open(POOL, encoding="utf-8", errors="ignore") as f:
    for line in f:
        p = line.strip().split("\t")
        if p and p[0]:
            pool.add(p[0].split()[0])
        if len(p) >= 5:
            cnt[p[4].strip().upper()] += 1

top = [o for o, _ in cnt.most_common(TOPN) if o in org2asn]
print("targeting:", len(top))

picked = []
for o in top:
    for s, e in ranges.get(org2asn[o], []):
        if len(picked) >= ADDRS:
            break
        n = e - s + 1
        if n <= 256:
            picked.append(s + random.randint(0, n - 1))
        else:
            for base in range(s, e + 1, 256):
                if len(picked) >= ADDRS:
                    break
                picked.append(random.randint(base, min(base + 255, e)))

random.seed(23)
random.shuffle(picked)

os.makedirs(OUTDIR, exist_ok=True)
buf, nfile, written = [], 1, 0

def flush():
    global buf, nfile
    if not buf:
        return
    path = os.path.join(OUTDIR, f"q_ac_asn_{STAMP}_{nfile:02d}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(buf) + "\n")
    print("wrote", path, len(buf))
    nfile += 1
    buf = []

for ipi in picked:
    try:
        ip = str(ipaddress.ip_address(ipi))
    except Exception:
        continue
    for port in PORTS:
        ep = f"{ip}:{port}"
        if ep in pool:
            continue
        buf.append(ep)
        written += 1
        if len(buf) >= CHUNK:
            flush()
flush()
print("total written:", written)
