import os
import re

REPO_ROOT = "D:/DEpinFarm"
REAL_POOL = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
ASSIGN_OUT = os.path.join(REPO_ROOT, "work", "assign_200.txt")

def parse_line(line):
    line = line.strip()
    if not line:
        return None
    parts = line.split("\t")
    
    cat = None
    for c in ["FAST", "MED", "SLOW"]:
        if c in parts:
            cat = c
            break
    if not cat:
        return None

    # Find latency
    # usually right before the tag
    cat_idx = parts.index(cat)
    lat = 999999
    if cat_idx > 0:
        val_str = parts[cat_idx - 1].strip()
        if val_str.isdigit():
            lat = int(val_str)
        else:
            # try to search all numeric tokens
            digits = [int(p) for p in parts if p.isdigit() and int(p) > 10 and int(p) != 3128 and int(p) != 8080]
            if digits:
                lat = digits[0]

    return {
        "line": line,
        "endpoint": parts[0].strip(),
        "cat": cat,
        "lat": lat
    }

def main():
    with open(REAL_POOL, "r", encoding="utf-8", errors="ignore") as f:
        lines = [l.strip() for l in f if l.strip()]

    parsed = []
    seen = set()
    for l in lines:
        p = parse_line(l)
        if p and p["endpoint"] not in seen:
            seen.add(p["endpoint"])
            parsed.append(p)

    fast = [p for p in parsed if p["cat"] == "FAST"]
    med = [p for p in parsed if p["cat"] == "MED"]
    slow = [p for p in parsed if p["cat"] == "SLOW"]

    fast.sort(key=lambda x: x["lat"])
    med.sort(key=lambda x: x["lat"])
    slow.sort(key=lambda x: x["lat"])

    print(f"Total parsed in real_pool: FAST={len(fast)}, MED={len(med)}, SLOW={len(slow)}")

    sorted_all = fast + med + slow
    top_400 = sorted_all[:400]

    cnt_fast = sum(1 for p in top_400 if p["cat"] == "FAST")
    cnt_med = sum(1 for p in top_400 if p["cat"] == "MED")
    cnt_slow = sum(1 for p in top_400 if p["cat"] == "SLOW")

    os.makedirs(os.path.dirname(ASSIGN_OUT), exist_ok=True)
    with open(ASSIGN_OUT, "w", encoding="utf-8") as f:
        for p in top_400:
            f.write(p["line"] + "\n")

    print("\n--- TOP 400 ASSIGNMENT LIST WRITTEN ---")
    print(f"File: {ASSIGN_OUT}")
    print(f"Total: {len(top_400)}")
    print(f"FAST count: {cnt_fast}")
    print(f"MED count:  {cnt_med}")
    print(f"SLOW count: {cnt_slow}")

if __name__ == "__main__":
    main()
