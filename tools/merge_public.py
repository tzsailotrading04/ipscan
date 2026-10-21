import re, os
def ips(path):
    s=set()
    if not os.path.exists(path): return s
    for line in open(path, errors="ignore"):
        m=re.search(r'(\d{1,3}(?:\.\d{1,3}){3})', line)
        if m: s.add(m.group(1))
    return s
seen = ips("master_pool.txt") | ips("ip/public_pool.txt.bak")
add = []
for line in open("ip/public_pool.txt", errors="ignore"):
    m=re.search(r'(\d{1,3}(?:\.\d{1,3}){3})', line)
    if not m: continue
    if m.group(1) in seen: continue
    seen.add(m.group(1)); add.append(line.rstrip("\n"))
with open("master_pool.txt","a") as f:
    for l in add: f.write(l+"\n")
print("master_pool now:", sum(1 for _ in open("master_pool.txt")))
print("newly added:", len(add))
