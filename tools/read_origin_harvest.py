import subprocess

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout

def main():
    # List files in origin/main:ip/harvest/
    ls_tree = run(["git", "-C", r"D:\DEpinFarm", "ls-tree", "origin/main", "ip/harvest/"])
    part_files = []
    stat_files = []
    for line in ls_tree.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            fname = parts[3]
            if "verified_alive_part_" in fname and fname.endswith(".txt") and "_w" not in fname:
                part_files.append(fname)
            elif "shodan_stats_v98_" in fname and fname.endswith(".txt") and "_w" not in fname:
                stat_files.append(fname)

    total_proxies = set()
    shard_counts = {}
    for pf in sorted(part_files):
        content = run(["git", "-C", r"D:\DEpinFarm", "show", f"origin/main:{pf}"])
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        shard_tag = pf.replace("ip/harvest/verified_alive_part_", "").replace(".txt", "")
        shard_counts[shard_tag] = len(lines)
        for l in lines:
            total_proxies.add(l.split("\t")[0])

    print("=== KAGGLE HARVEST PER SHARD ===")
    for tag in sorted(shard_counts.keys()):
        print(f"  Shard {tag}: {shard_counts[tag]} verified alive proxies")

    total_scanned_ips = 0
    total_cands = 0
    total_req_s = 0.0
    for sf in sorted(stat_files):
        try:
            content = run(["git", "-C", r"D:\DEpinFarm", "show", f"origin/main:{sf}"])
            for line in content.splitlines():
                if line.startswith("offset="):
                    total_scanned_ips += int(line.split("=")[1])
                elif line.startswith("cands="):
                    total_cands += int(line.split("=")[1])
                elif line.startswith("req_s="):
                    total_req_s += float(line.split("=")[1])
        except Exception:
            pass

    print("\n=== TOTAL HARVEST METRICS ===")
    print(f"Total Unique Verified Alive Proxies in GitHub Pool: {len(total_proxies)}")
    print(f"Total Scanned Target IPs across Shards:           {total_scanned_ips:,}")
    print(f"Total Direct Candidates Identified:               {total_cands:,}")
    print(f"Total Fleet Scan Velocity:                        {total_req_s:,.1f} req/s")

if __name__ == "__main__":
    main()
