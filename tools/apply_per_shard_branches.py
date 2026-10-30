#!/usr/bin/env python3
import os
import re

REPO_ROOT = r"D:\DEpinFarm"
MASTER = os.path.join(REPO_ROOT, "kaggle", "cl_shodan", "run.py")

with open(MASTER, "r", encoding="utf-8") as f:
    text = f.read()

# 1. Update OUT_BRANCH definition
if "OUT_BRANCH =" not in text:
    old_shard_tag = 'SHARD_TAG = f"{SHARD_IDX:02d}"'
    new_shard_tag = 'SHARD_TAG = f"{SHARD_IDX:02d}"\nOUT_BRANCH = f"out/sh{SHARD_TAG}"'
    assert old_shard_tag in text, "old_shard_tag not found!"
    text = text.replace(old_shard_tag, new_shard_tag, 1)

# 2. Replace git_sync_and_push with per-shard branch push function
old_push_fn = """def git_sync_and_push(msg):
    try:
        subprocess.run(["git", "-C", REPO, "add", "-A"], check=False)
        st = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True)
        if not st.stdout.strip():
            return True
        c_res = subprocess.run(["git", "-C", REPO, "commit", "-m", msg], capture_output=True, text=True)
        if c_res.returncode != 0 and ("nothing to commit" in c_res.stdout or "nothing to commit" in c_res.stderr):
            return True

        for attempt in range(1, 16):
            subprocess.run(["git", "-C", REPO, "fetch", "origin", "main"], check=False)
            m_res = subprocess.run(["git", "-C", REPO, "merge", "--no-edit", "origin/main"], capture_output=True, text=True)
            if m_res.returncode != 0:
                subprocess.run(["git", "-C", REPO, "merge", "--abort"], capture_output=True)
                backoff = min(60, 2 ** attempt) * random.uniform(0.5, 1.5)
                time.sleep(backoff)
                continue

            p_res = subprocess.run(["git", "-C", REPO, "push", "origin", "HEAD:main"], capture_output=True, text=True)
            if p_res.returncode == 0:
                return True
            print(f"[GIT ERROR] push failed attempt {attempt}/15: {p_res.stderr.strip()}", file=sys.stderr, flush=True)
            backoff = min(60, 2 ** attempt) * random.uniform(0.5, 1.5)
            time.sleep(backoff)
        return False
    except Exception as e:
        print(f"[GIT EXCEPTION] {e}", file=sys.stderr, flush=True)
        return False"""

new_push_fn = """def git_sync_and_push(msg):
    try:
        # Fetch only its own branch
        subprocess.run(["git", "-C", REPO, "fetch", "origin", f"{OUT_BRANCH}:{OUT_BRANCH}"], capture_output=True, check=False)

        # Stage its part, stats, progress, and stage files
        patterns = [
            f"ip/harvest/verified_alive_part_{SHARD_TAG}*.txt",
            f"ip/harvest/shodan_stats_v98_{SHARD_TAG}*.txt",
            f"ip/harvest/shodan_progress_v98_{SHARD_TAG}*.txt",
            f"ip/harvest/stage_{SHARD_TAG}.txt",
        ]
        for pat in patterns:
            subprocess.run(["git", "-C", REPO, "add", pat], capture_output=True, check=False)

        st = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True)
        if not st.stdout.strip():
            return True

        c_res = subprocess.run(["git", "-C", REPO, "commit", "-m", msg], capture_output=True, text=True)
        if c_res.returncode != 0 and ("nothing to commit" in c_res.stdout or "nothing to commit" in c_res.stderr):
            return True

        # Push directly to out/sh<SHARD_TAG> - no rebase, no retry loop needed
        p_res = subprocess.run(["git", "-C", REPO, "push", "origin", f"HEAD:refs/heads/{OUT_BRANCH}"], capture_output=True, text=True)
        if p_res.returncode == 0:
            return True
        # If remote exists and diverged, force push to own isolated branch
        p_res = subprocess.run(["git", "-C", REPO, "push", "-f", "origin", f"HEAD:refs/heads/{OUT_BRANCH}"], capture_output=True, text=True)
        return p_res.returncode == 0
    except Exception as e:
        print(f"[GIT EXCEPTION] {e}", file=sys.stderr, flush=True)
        return False"""

assert old_push_fn in text, "old_push_fn not found in MASTER!"
text = text.replace(old_push_fn, new_push_fn, 1)

with open(MASTER, "w", encoding="utf-8") as f:
    f.write(text)

print("Updated master kaggle/cl_shodan/run.py successfully.")

# Propagate to all 34 shards
for s in range(34):
    stag = f"{s:02d}"
    shard_run = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{stag}", "run.py")
    shard_content = text
    shard_content = re.sub(r'SHARD_TAG = "[^"]+"', f'SHARD_TAG = "{stag}"', shard_content)
    shard_content = re.sub(r'shard_idx = \d+', f'shard_idx = {s}', shard_content)
    with open(shard_run, "w", encoding="utf-8") as sf:
        sf.write(shard_content)

print("Propagated to all 34 shards (00..33).")

# Update tools/fleet_cycle.py with merge_out_branches
FC_PATH = os.path.join(REPO_ROOT, "tools", "fleet_cycle.py")
with open(FC_PATH, "r", encoding="utf-8") as f:
    fc_text = f.read()

merge_fn_code = """last_merge_ts = 0

def merge_out_branches():
    \"\"\"Every 300s, fetch all out/sh* branches and merge their files into main, then push once.\"\"\"
    global last_merge_ts
    now = time.time()
    if (now - last_merge_ts) < 300:
        return False

    print(f"\\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] [MERGE] Fetching all out/sh* branches...")
    run_cmd(f'git -C "{REPO_ROOT}" fetch origin "+refs/heads/out/sh*:refs/remotes/origin/out/sh*" --prune --quiet')

    out, err, code = run_cmd(f'git -C "{REPO_ROOT}" branch -r --list "origin/out/sh*"')
    remote_branches = [b.strip() for b in out.splitlines() if b.strip()]

    if not remote_branches:
        print("[MERGE] No out/sh* branches found on remote.")
        last_merge_ts = now
        return False

    print(f"[MERGE] Found {len(remote_branches)} remote shard branches to merge.")
    merged_count = 0
    for rb in remote_branches:
        branch_name = rb.split("/")[-1]
        tag = branch_name.replace("sh", "")
        c_out, c_err, c_code = run_cmd(
            f'git -C "{REPO_ROOT}" checkout {rb} -- '
            f'"ip/harvest/verified_alive_part_{tag}*.txt" '
            f'"ip/harvest/shodan_stats_v98_{tag}*.txt" '
            f'"ip/harvest/shodan_progress_v98_{tag}*.txt" '
            f'"ip/harvest/stage_{tag}.txt"'
        )
        if c_code == 0:
            merged_count += 1

    new_pool, pool_total = harvest_and_dedupe()

    run_cmd(f'git -C "{REPO_ROOT}" add ip/harvest/ real_pool.txt cache/ work/FLEET_CYCLE.txt')
    st_out, _, _ = run_cmd(f'git -C "{REPO_ROOT}" status --porcelain')
    if st_out:
        msg = f"v98.188 merge {merged_count} shard branches, pool={pool_total} (+{new_pool})"
        run_cmd(f'git -C "{REPO_ROOT}" commit -m "{msg}"')
        p_out, p_err, p_code = run_cmd(f'git -C "{REPO_ROOT}" push origin main')
        if p_code == 0:
            print(f"[MERGE] Pushed merged shard files to main (pool={pool_total}, +{new_pool}).")
        else:
            print(f"[MERGE] Push to main failed: {p_err or p_out}")
    else:
        print("[MERGE] No file changes after merging shard branches.")

    last_merge_ts = now
    return True
"""

if "def merge_out_branches():" not in fc_text:
    # Insert right before def main():
    assert "def main():" in fc_text, "def main() not found in fleet_cycle.py!"
    fc_text = fc_text.replace("def main():", merge_fn_code + "\ndef main():", 1)

old_fc_main = """def main():
    seen = load_seen_set()
    cycle = 1

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_single_cycle(cycle, seen)
        return

    while True:
        try:
            run_single_cycle(cycle, seen)
            cycle += 1
            time.sleep(900)"""

new_fc_main = """def main():
    seen = load_seen_set()
    cycle = 1
    last_cycle_t = 0

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        merge_out_branches()
        run_single_cycle(cycle, seen)
        return

    while True:
        try:
            merge_out_branches()
            now = time.time()
            if (now - last_cycle_t) >= 900:
                run_single_cycle(cycle, seen)
                cycle += 1
                last_cycle_t = now
            time.sleep(30)"""

if old_fc_main in fc_text:
    fc_text = fc_text.replace(old_fc_main, new_fc_main, 1)

with open(FC_PATH, "w", encoding="utf-8") as f:
    f.write(fc_text)

print("Updated tools/fleet_cycle.py with merge_out_branches successfully.")
