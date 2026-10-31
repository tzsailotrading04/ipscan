import os, random, ipaddress, collections

TSV = "data/ip2asn-v4-u32.tsv"
POOL = "ip/harvest/real_pool.txt"
OUTDIR = "ip/harvest/queue"
LIMIT = 120000
PORTS = (443, 3128)
CHUNK = 40000
STAMP = "1793433000"
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
with open(POOL, encoding="utf-8", errors="ignore") as f:
    for line in f:
        p = line.strip().split("\t")
        if len(p) >= 5:
            cnt[p[4].strip().upper()] += 1

top = [o for o, _ in cnt.most_common(TOPN) if o in org2asn]
print("live orgs:", len(cnt), "targeting:", len(top))
for o in top[:12]:
    print("  ", o, cnt[o], "nodes")

picked = []
for o in top:
    for s, e in ranges.get(org2asn[o], []):
        if len(picked) >= LIMIT:
            break
        n = e - s + 1
        if n <= 256:
            picked.append(s + random.randint(0, n - 1))
        else:
            for base in range(s, e + 1, 256):
                if len(picked) >= LIMIT:
                    break
                hi = min(base + 255, e)
                picked.append(random.randint(base, hi))

pool = set()
with open(POOL, encoding="utf-8", errors="ignore") as f:
    for l in f:
        q = l.strip().split("\t")[0].split()[0] if l.strip() else ""
        if q:
            pool.add(q)

random.seed(5)
random.shuffle(picked)

os.makedirs(OUTDIR, exist_ok=True)
buf, nfile, written = [], 1, 0

def flush():
    global buf, nfile
    if not buf:
        return
    path = os.path.join(OUTDIR, f"q_aa_asn_{STAMP}_{nfile:02d}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(buf) + "\n")
    print("wrote", path, len(buf))
    nfile += 1
    buf = []

for ipi in picked:
    if written >= LIMIT:
        break
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
