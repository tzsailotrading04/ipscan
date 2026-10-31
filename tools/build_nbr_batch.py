import os, random, ipaddress

POOL = "ip/harvest/real_pool.txt"
OUTDIR = "ip/harvest/queue"
PORTS = (8080, 3128, 8888)
CHUNK = 40000
MAX_TOTAL = 180000
STAMP = "1793437000"

pool_eps = set()
pool_ips = set()
c24_set = set()

with open(POOL, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        ep = line.split("\t")[0].split()[0]
        if not ep:
            continue
        pool_eps.add(ep)
        ip = ep.split(":")[0]
        pool_ips.add(ip)
        try:
            net = ipaddress.ip_network(f"{ip}/24", strict=False)
            c24_set.add(net)
        except Exception:
            pass

print("collected /24s:", len(c24_set))

# Deterministic shuffle for reproducibility
c24_list = sorted(list(c24_set), key=lambda x: int(x.network_address))
random.seed(42)
random.shuffle(c24_list)

os.makedirs(OUTDIR, exist_ok=True)
buf, nfile, written = [], 1, 0

def flush():
    global buf, nfile
    if not buf:
        return
    path = os.path.join(OUTDIR, f"q_ad_nbr_{STAMP}_{nfile:02d}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(buf) + "\n")
    print("wrote", path, len(buf))
    nfile += 1
    buf = []

stop = False
for net in c24_list:
    if stop or written >= MAX_TOTAL:
        break
    base_int = int(net.network_address)
    # Available host integers inside this /24 (1..254)
    # Pick 20 random addresses not in pool_ips
    candidates = [base_int + i for i in range(1, 255)]
    random.shuffle(candidates)
    
    picked_for_net = []
    for cand in candidates:
        cand_ip = str(ipaddress.ip_address(cand))
        if cand_ip in pool_ips:
            continue
        picked_for_net.append(cand_ip)
        if len(picked_for_net) >= 20:
            break

    for ip_str in picked_for_net:
        if written >= MAX_TOTAL:
            stop = True
            break
        for port in PORTS:
            ep = f"{ip_str}:{port}"
            if ep in pool_eps:
                continue
            buf.append(ep)
            written += 1
            if len(buf) >= CHUNK:
                flush()
            if written >= MAX_TOTAL:
                stop = True
                break

flush()
print("total written:", written)
