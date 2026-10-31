import os
import re

BULK_FILE = "ip/harvest/bulk_all.txt"
POOL_FILE = "ip/harvest/real_pool.txt"
OUTDIR = "ip/harvest/queue"
CHUNK = 40000
MAX_TOTAL = 200000
STAMP = "1793440000"

pool_set = set()
if os.path.exists(POOL_FILE):
    with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line:
                ep = line.split("\t")[0].split()[0]
                pool_set.add(ep)

print(f"Loaded {len(pool_set)} endpoints from real_pool.txt")

os.makedirs(OUTDIR, exist_ok=True)

buf = []
nfile = 1
written = 0
dropped = 0
seen = set()

def flush():
    global buf, nfile
    if not buf:
        return
    path = os.path.join(OUTDIR, f"q_a1_bulk_{STAMP}_{nfile:02d}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(buf) + "\n")
    print(f"wrote {path} {len(buf)} lines")
    nfile += 1
    buf = []

ip_port_re = re.compile(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})$')

if os.path.exists(BULK_FILE):
    with open(BULK_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if written >= MAX_TOTAL:
                break
            line = line.strip().split("\t")[0].split()[0]
            m = ip_port_re.match(line)
            if not m:
                continue
            ip, port = m.groups()
            p_int = int(port)
            if not (1 <= p_int <= 65535):
                continue
            octets = [int(o) for o in ip.split('.')]
            if not all(0 <= o <= 255 for o in octets):
                continue
            
            ep = f"{ip}:{port}"
            if ep in seen:
                continue
            seen.add(ep)

            if ep in pool_set:
                dropped += 1
                continue

            buf.append(ep)
            written += 1
            if len(buf) >= CHUNK:
                flush()

flush()

print(f"Total written: {written}")
print(f"Total dropped (already known in real_pool): {dropped}")
