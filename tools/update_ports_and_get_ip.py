"""
update_ports_and_get_ip.py
Updates all 20 kaggle/cl_shodan_XX/run.py files:
1. DIRECT_PORTS = [80, 443, 3128, 8080, 8000, 1080, 8118, 8888]
2. get_ip(offset) -> strided indexing into subnets: (offset >> 8) % len(subnets), offset & 0xFF
3. total_ips = len(subnets) * 256 (20,909,824 IPs per shard)
4. Checks syntax with py_compile
"""
import os
import py_compile

ROOT = r"D:\DEpinFarm"

NEW_PORTS = "DIRECT_PORTS = [80, 443, 3128, 8080, 8000, 1080, 8118, 8888]"
OLD_PORTS = "DIRECT_PORTS = [80, 443]"

NEW_GET_IP_BLOCK = """    BASE_TOTAL_IPS = len(subnets) * 256
    total_ips = BASE_TOTAL_IPS
    log(f"Hosting subnets={len(subnets):,} total_ips={total_ips:,} for shard {SHARD_TAG}")

    def get_ip(offset):
        # Deterministic, strided indexing into shard's hosting subnets (81,679 subnets * 256 IPs)
        subnet_idx = (offset >> 8) % len(subnets)
        host = offset & 0xFF
        return f"{subnets[subnet_idx]}.{host}"

    """

def update_shard(idx):
    tag = f"{idx:02d}"
    path = os.path.join(ROOT, "kaggle", f"cl_shodan_{tag}", "run.py")
    with open(path, "r", encoding="utf-8") as f:
        code = f.read()

    # 1. Update DIRECT_PORTS
    if OLD_PORTS in code:
        code = code.replace(OLD_PORTS, NEW_PORTS)
    elif NEW_PORTS not in code:
        raise ValueError(f"DIRECT_PORTS line not found in {path}")

    # 2. Update get_ip block in async_main
    s_marker = "    BASE_TOTAL_IPS = len(subnets) * 256"
    e_marker = '    prog_file = os.path.join(REPO, "ip", "harvest", f"shodan_progress_{OUT_PREFIX}{SHARD_TAG}.txt")'

    s_idx = code.find(s_marker)
    e_idx = code.find(e_marker)
    if s_idx == -1 or e_idx == -1:
        raise ValueError(f"get_ip markers not found in {path}")

    code = code[:s_idx] + NEW_GET_IP_BLOCK + code[e_idx:]

    with open(path, "w", encoding="utf-8") as f:
        f.write(code)

    py_compile.compile(path, doraise=True)
    print(f"Shard {tag}: updated ports and get_ip successfully.")

if __name__ == "__main__":
    for i in range(20):
        update_shard(i)
    print("ALL 20 SHARDS UPDATED AND COMPILED CLEANLY.")
