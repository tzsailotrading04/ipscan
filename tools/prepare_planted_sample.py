"""
tools/prepare_planted_sample.py
Prepares a 100,000-IP real random sample with 500 confirmed-live known-good proxies shuffled into it.
Ground truth metadata is saved to benchmark_ground_truth.json.
"""
import json
import os
import random

ROOT = r"D:\DEpinFarm"
PLANTED_SRC = os.path.join(ROOT, "ip", "harvest", "planted_500_verified.txt")
SUBNETS_SRC = os.path.join(ROOT, "data", "hosting_subnets.txt")
OUT_IPS_PATH = os.path.join(ROOT, "ip", "harvest", "benchmark_100k_planted.txt")
OUT_GT_PATH = os.path.join(ROOT, "ip", "harvest", "benchmark_ground_truth.json")

def main():
    planted = {}
    with open(PLANTED_SRC, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and ":" in line:
                ip, port = line.split(":")
                planted[ip] = int(port)

    assert len(planted) == 500, f"Expected 500 planted proxies, got {len(planted)}"
    print(f"Loaded {len(planted)} confirmed-live planted proxies.")

    with open(SUBNETS_SRC, "r", encoding="utf-8") as f:
        subnets = list(set(line.strip() for line in f if line.strip() and not line.startswith("#")))

    random.seed(42)
    random.shuffle(subnets)

    real_ips = set()
    for s in subnets:
        if len(real_ips) >= 99500:
            break
        for _ in range(4):
            h = random.randint(1, 254)
            ip = f"{s}.{h}"
            if ip not in planted:
                real_ips.add(ip)
            if len(real_ips) >= 99500:
                break

    real_list = list(real_ips)[:99500]
    print(f"Generated {len(real_list)} real un-scanned internet IPs.")

    # Combine and shuffle
    all_ips = list(planted.keys()) + real_list
    assert len(all_ips) == 100000, f"Expected 100000 total IPs, got {len(all_ips)}"
    random.seed(1337)
    random.shuffle(all_ips)

    with open(OUT_IPS_PATH, "w", encoding="utf-8") as f:
        for ip in all_ips:
            f.write(ip + "\n")

    ground_truth = {
        "total_ips": len(all_ips),
        "planted_count": len(planted),
        "real_count": len(real_list),
        "planted_proxies": planted,
    }

    with open(OUT_GT_PATH, "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2)

    print(f"Saved {len(all_ips)} IPs to {OUT_IPS_PATH}")
    print(f"Saved ground truth metadata to {OUT_GT_PATH}")

if __name__ == "__main__":
    main()
