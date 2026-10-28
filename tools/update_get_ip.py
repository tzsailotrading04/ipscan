import os

with open('kaggle/cl_shodan/run.py', 'r', encoding='utf-8') as fp:
    content = fp.read()

target = '''    EXTENDED_TOTAL_IPS = 2_000_000_000  # 2 Billion IPs per shard
    total_ips = EXTENDED_TOTAL_IPS
    log(f"base_ips={BASE_TOTAL_IPS:,} total_ips={total_ips:,} (2 Billion target)")

    def get_ip(offset):
        if offset % 2 == 0:
            # Systematic strided subnets across public IPv4
            idx = (offset // 2) % BASE_TOTAL_IPS
            s_idx = idx // 256
            return f"{subnets[s_idx]}.{idx % 256}"
        else:
            # Genuinely uniform random IPv4 (1-223, /16, host)
            rnd_offset = offset // 2
            x = (rnd_offset * 0xbf58476d1ce4e5b9 + 0x9e3779b97f4a7c15 + (SHARD_IDX * 0x517cc1b727220a95)) & 0xFFFFFFFFFFFFFFFF
            x = (x ^ (x >> 30)) * 0x94d049bb133111eb & 0xFFFFFFFFFFFFFFFF
            x = x ^ (x >> 31)
            a = 1 + (x % 223)
            if a in (10, 127):
                a = 11
            b = (x >> 8) & 0xFF
            c = (x >> 16) & 0xFF
            if a == 169 and b == 254: b = 253
            if a == 172 and (16 <= b <= 31): b = 32
            if a == 192 and b == 168: b = 167
            if a == 100 and (64 <= b <= 127): b = 128
            if a == 198 and (b in (18, 19)): b = 20
            d = 1 + ((x >> 24) % 254)
            return f"{a}.{b}.{c}.{d}"'''

replacement = '''    EXTENDED_TOTAL_IPS = 100_000_000  # 100M IPs per shard = 2 Billion Fleet Target
    total_ips = EXTENDED_TOTAL_IPS
    log(f"base_ips={BASE_TOTAL_IPS:,} total_ips={total_ips:,} (2 Billion Fleet Target: 100M/shard)")

    def get_ip(offset):
        # 100% Genuinely uniform random IPv4 across 1-223, /16, host
        # Deterministic SplitMix64 keyed on (offset, SHARD_IDX) for 100% git cursor persistence
        x = (offset * 0xbf58476d1ce4e5b9 + 0x9e3779b97f4a7c15 + (SHARD_IDX * 0x517cc1b727220a95)) & 0xFFFFFFFFFFFFFFFF
        x = (x ^ (x >> 30)) * 0x94d049bb133111eb & 0xFFFFFFFFFFFFFFFF
        x = x ^ (x >> 31)
        a = 1 + (x % 223)
        if a in (10, 127):
            a = 11
        b = (x >> 8) & 0xFF
        c = (x >> 16) & 0xFF
        if a == 169 and b == 254: b = 253
        if a == 172 and (16 <= b <= 31): b = 32
        if a == 192 and b == 168: b = 167
        if a == 100 and (64 <= b <= 127): b = 128
        if a == 198 and (b in (18, 19)): b = 20
        d = 1 + ((x >> 24) % 254)
        return f"{a}.{b}.{c}.{d}"'''

c_norm = content.replace('\r\n', '\n')
t_norm = target.replace('\r\n', '\n')
r_norm = replacement.replace('\r\n', '\n')

if t_norm in c_norm:
    c_norm = c_norm.replace(t_norm, r_norm)
    print("Found and replaced in base run.py")
else:
    print("ERROR: target not found in base run.py")

with open('kaggle/cl_shodan/run.py', 'w', encoding='utf-8') as fp:
    fp.write(c_norm)

# Propagate to all 20 shard files
for i in range(20):
    kdir = os.path.join('kaggle', f'cl_shodan_{i:02d}')
    shard_content = c_norm.replace('shard_str = "0"', f'shard_str = "{i}"')
    shard_content = shard_content.replace('shard_str = os.environ.get("SHARD_INDEX", os.environ.get("SLICE_IDX", ""))', f'shard_str = "{i}"')
    p = os.path.join(kdir, 'run.py')
    with open(p, 'w', encoding='utf-8') as fp:
        fp.write(shard_content)
    print(f"Propagated to shard {i:02d}")
