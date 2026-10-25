import glob
import os
import subprocess
import sys
import time

REPO = r"D:\DEpinFarm"
H = os.path.join(REPO, "ip", "harvest")
STALE_MARK = "/3350000"
NEW_MARK = "v98.2"
QUIET_MIN = 8
MAX_WAIT = 45 * 60
SETTLE = 420


def run(args):
    return subprocess.run(args, cwd=REPO, capture_output=True, text=True)


def pull():
    run(["git", "pull", "--rebase", "--autostash", "origin", "main"])


def recent_subjects(minutes):
    r = run(["git", "log", f"--since={minutes} minutes ago", "--format=%s", "origin/main"])
    return [l for l in r.stdout.splitlines() if l.strip()]


def stats_count():
    return len(glob.glob(os.path.join(H, "shodan_stats_v98_*.txt")))


def main():
    t0 = time.time()
    saw_stale = False
    reason = "TIMEOUT"
    print(f"Watching origin/main up to {MAX_WAIT // 60} min for stale v94 pods to die...")
    print(f"Signal: commits containing '{STALE_MARK}' must stop arriving\n")

    while time.time() - t0 < MAX_WAIT:
        pull()
        subs = recent_subjects(QUIET_MIN)
        stale = sum(1 for s in subs if STALE_MARK in s)
        new = sum(1 for s in subs if NEW_MARK in s)
        n_stats = stats_count()
        el = int(time.time() - t0)
        print(f"[{el:4d}s] last{QUIET_MIN}m: stale_v94={stale:2d}  v98.2={new:2d}  stats_files={n_stats}")
        if stale > 0:
            saw_stale = True
        if n_stats > 0:
            reason = "NEW CODE ALREADY LIVE"
            break
        if saw_stale and stale == 0:
            reason = "STALE PODS GONE"
            break
        time.sleep(60)

    print(f"\nLOOP EXIT: {reason}")

    if reason == "NEW CODE ALREADY LIVE":
        print("v98.2 pods already running - skipping re-push")
    else:
        print("Re-pushing all 20 shards...")
        r = subprocess.run([sys.executable, os.path.join(REPO, "tools", "deploy_shodan_v98.py")],
                           cwd=REPO, text=True)
        print(f"deploy exit={r.returncode}")

    print(f"\nSettling {SETTLE}s...")
    time.sleep(SETTLE)

    print("\nRunning verifier...")
    subprocess.run([sys.executable, os.path.join(REPO, "tools", "verify_v982.py"), "600"], cwd=REPO)

    n = stats_count()
    print(f"\nFINAL stats_files={n}")
    if n == 0:
        print("RESULT: nothing running - report the loop log")
        sys.exit(2)
    print("RESULT: v98.2 IS RUNNING")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
