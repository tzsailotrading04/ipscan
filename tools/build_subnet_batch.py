import os, random, ipaddress

SRC = "data/res_subnets.txt"
OUTDIR = "ip/harvest/queue"
POOL = "ip/harvest/real_pool.txt"
LIMIT = 120000
PORTS = (443, 3128)
CHUNK = 40000
STAMP = "1793430000"

pool = set()
if os.path.exists(POOL):
    with open(POOL, encoding="utf-8", errors="ignore") as f:
        for l in f:
            p = l.strip().split("\t")[0].split()[0] if l.strip() else ""
            if p:
                pool.add(p)

nets = []
with open(SRC, encoding="utf-8", errors="ignore") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            if "/" in line:
                nets.append(ipaddress.ip_network(line, strict=False))
            elif line.count(".") == 2:
                nets.append(ipaddress.ip_network(line + ".0/24", strict=False))
            else:
                parts = line.replace("\t", " ").split()
                if len(parts) >= 2:
                    a = ipaddress.ip_address(parts[0]); b = ipaddress.ip_address(parts[1])
                    nets.extend(ipaddress.summarize_address_range(a, b))
        except Exception:
            continue

print("subnets parsed:", len(nets))
random.seed(7)
random.shuffle(nets)

os.makedirs(OUTDIR, exist_ok=True)
buf, nfile, written = [], 1, 0

def flush():
    global buf, nfile
    if not buf:
        return
    path = os.path.join(OUTDIR, f"q_res_{STAMP}_{nfile:02d}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(buf) + "\n")
    print("wrote", path, len(buf))
    nfile += 1
    buf = []

for net in nets:
    if written >= LIMIT:
        break
    hosts = net.num_addresses - 2
    if hosts <= 0:
        continue
    try:
        ip = str(net.network_address + random.randint(1, hosts))
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
