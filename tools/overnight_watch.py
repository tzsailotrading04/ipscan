import os, sys, time, glob, datetime

REPO_ROOT = r"D:\DEpinFarm"
LOG_FILE = os.path.join(REPO_ROOT, "work", "overnight_watch.log")
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
PARTS_DIR = os.path.join(REPO_ROOT, "ip", "harvest")

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

def count_lines(filepath):
    if not os.path.exists(filepath):
        return 0
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0

def get_readings(window_seconds=1800):
    # 1. real_pool.txt line count
    pool_lines = count_lines(POOL_FILE)

    # 2. part files modified in last window_seconds
    now = time.time()
    part_files = glob.glob(os.path.join(PARTS_DIR, "verified_alive_part_*.txt"))
    
    touched_count = 0
    total_part_lines = 0

    for pf in part_files:
        try:
            mtime = os.path.getmtime(pf)
            if (now - mtime) <= window_seconds:
                touched_count += 1
            total_part_lines += count_lines(pf)
        except Exception:
            continue

    return pool_lines, touched_count, total_part_lines

def log_msg(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_line = f"[{ts}] {msg}"
    print(full_line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(full_line + "\n")
    except Exception as e:
        print(f"Error writing to log file: {e}", flush=True)

def main():
    log_msg("=== Overnight Watch Started (Target: 18 readings / 9 hours / strictly read-only) ===")
    
    total_readings = 18
    interval_seconds = 1800 # 30 minutes

    for i in range(1, total_readings + 1):
        pool_lines, touched_count, total_part_lines = get_readings(window_seconds=interval_seconds)
        
        warning_tag = ""
        if touched_count < 25:
            warning_tag = " [WARNING: THINNING]"
            
        reading_str = (
            f"Reading {i:02d}/18: "
            f"real_pool={pool_lines:,} | "
            f"parts_touched_30m={touched_count} | "
            f"total_part_lines={total_part_lines:,}"
            f"{warning_tag}"
        )
        log_msg(reading_str)

        if i < total_readings:
            time.sleep(interval_seconds)

    log_msg("=== Overnight watch has ended. All 18 readings completed. ===")

if __name__ == "__main__":
    main()
