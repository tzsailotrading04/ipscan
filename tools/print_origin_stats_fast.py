import subprocess
import datetime

def parse_stats(ref, path):
    res = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True, errors="ignore")
    if res.returncode != 0:
        return None
    raw = res.stdout.strip()
    if not raw:
        return None
    parts = raw.split()
    if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
        return int(parts[1]), int(parts[2])
    if "=" in raw:
        kv = dict(l.split("=", 1) for l in raw.splitlines() if "=" in l)
        s = int(kv.get("offset", 0)) if kv.get("offset", "").isdigit() else 0
        c = int(kv.get("cands", 0)) if kv.get("cands", "").isdigit() else 0
        return s, c
    return None

def main():
    utc_now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print("=== SUMMED SCANNED AND GENUINE DIRECT FROM origin/out/shNN ===")
    print("UTC Time:", utc_now)
    print()
    hdr = f"{'Shard':<6} | {'w0 Scan':<12} | {'w1 Scan':<12} | {'Summed Scanned':<15} | {'w0 Gen':<8} | {'w1 Gen':<8} | {'Summed Genuine':<14} | {'Source Path'}"
    print(hdr)
    print("-" * 98)

    tot_s = 0
    tot_g = 0

    for i in range(20):
        tag = f"{i:02d}"
        ref = f"origin/out/sh{tag}"

        res0 = parse_stats(ref, f"work/sh{tag}_w0_stats.txt")
        res1 = parse_stats(ref, f"work/sh{tag}_w1_stats.txt")
        src = "work/shNN_w*_stats.txt"

        if res0 is None or res1 is None:
            res0 = parse_stats(ref, f"ip/harvest/shodan_stats_v98_{tag}_w0.txt")
            res1 = parse_stats(ref, f"ip/harvest/shodan_stats_v98_{tag}_w1.txt")
            src = f"shodan_stats_v98_{tag}_w*.txt"

        w0_s, w0_g = res0 if res0 else (0, 0)
        w1_s, w1_g = res1 if res1 else (0, 0)

        sum_s = w0_s + w1_s
        sum_g = w0_g + w1_g
        tot_s += sum_s
        tot_g += sum_g

        print(f"sh{tag:<4} | {w0_s:<12,d} | {w1_s:<12,d} | {sum_s:<15,d} | {w0_g:<8,d} | {w1_g:<8,d} | {sum_g:<14,d} | {src}")

    print("-" * 98)
    print(f"{'TOTAL':<6} | {'-':<12} | {'-':<12} | {tot_s:<15,d} | {'-':<8} | {'-':<8} | {tot_g:<14,d} |")
    print("-" * 98)

if __name__ == "__main__":
    main()
