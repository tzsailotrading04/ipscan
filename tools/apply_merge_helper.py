import os
import glob
import re

SHARD_GIT_HELPER = '''def git_sync_and_push(msg):
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
        return False

'''

OLD_SHARD_PUSH_BLOCK = '''        # Push to git every 30s
        now = time.time()
        if now - last_push_t >= 30:
            last_push_t = now
            try:
                subprocess.run(["git", "-C", REPO, "add", "ip/harvest/"], check=False)
                res = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True)
                if res.stdout.strip():
                    subprocess.run(["git", "-C", REPO, "commit", "-m", f"{ENGINE_VER} shard_{SHARD_TAG}: offset={total_offset} cands={total_cands} random_loop"], check=False)
                    for _ in range(5):
                        subprocess.run(["git", "-C", REPO, "pull", "--rebase", "origin", "main"], check=False)
                        p_res = subprocess.run(["git", "-C", REPO, "push", "origin", "main"], check=False)
                        if p_res.returncode == 0:
                            break
                        time.sleep(2)
            except Exception: pass'''

NEW_SHARD_PUSH_BLOCK = '''        # Push to git only when this shard's own output file changed, at most once per 10 minutes
        now = time.time()
        if now - last_push_t >= 600:
            cur_sig = (os.path.getmtime(shard_part), os.path.getsize(shard_part)) if os.path.exists(shard_part) else None
            if cur_sig is not None and cur_sig != last_shard_sig:
                last_push_t = now
                commit_msg = f"{ENGINE_VER} shard_{SHARD_TAG}: offset={total_offset} cands={total_cands} random_loop"
                if git_sync_and_push(commit_msg):
                    last_shard_sig = cur_sig'''

def update_shard(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Insert git_sync_and_push above def run_master():
    target_header = "def run_master():"
    if "def git_sync_and_push(msg):" not in content:
        if target_header not in content:
            raise ValueError(f"Could not find run_master in {path}")
        content = content.replace(target_header, SHARD_GIT_HELPER + target_header, 1)

    # 2. Update last_push_t initialization in run_master
    old_init = "    last_push_t = time.time()"
    new_init = "    shard_part = os.path.join(REPO, \"ip\", \"harvest\", f\"verified_alive_part_{SHARD_TAG}.txt\")\n    last_shard_sig = (os.path.getmtime(shard_part), os.path.getsize(shard_part)) if os.path.exists(shard_part) else None\n    last_push_t = time.time()"
    if old_init in content:
        content = content.replace(old_init, new_init, 1)

    # 3. Replace push block
    # Normalize CRLF / LF for matching
    content_norm = content.replace("\r\n", "\n")
    old_push_norm = OLD_SHARD_PUSH_BLOCK.replace("\r\n", "\n")
    if old_push_norm in content_norm:
        content_norm = content_norm.replace(old_push_norm, NEW_SHARD_PUSH_BLOCK.replace("\r\n", "\n"))
    else:
        raise ValueError(f"Could not find old push block in {path}")

    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content_norm)
    print(f"Updated {path}")

# Harvest file
HARVEST_GIT_SECTION_OLD = '''# ------------------------------------------------------------------------------
# GIT HELPER (PULL, ADD, COMMIT, PUSH WITH 3 RETRIES & JITTER)
# ------------------------------------------------------------------------------
def git_pull_repo():
    log("Pulling latest repo updates from origin/main...")
    r = subprocess.run(["git", "-C", REPO, "pull", "--rebase", "origin", "main"], capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(["git", "-C", REPO, "rebase", "--abort"], capture_output=True)
        subprocess.run(["git", "-C", REPO, "fetch", "origin", "main"], capture_output=True)
        subprocess.run(["git", "-C", REPO, "merge", "--no-edit", "-X", "ours", "origin/main"], capture_output=True)
        log("Pulled via merge fallback.")
    else:
        log("Pulled successfully via rebase.")

def git_sync_and_push(msg):
    try:
        subprocess.run(["git", "-C", REPO, "add", "-A"], check=False)
        st = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True)
        has_changes = any(l.strip() and not l.startswith("??") for l in st.stdout.splitlines())
        if not has_changes:
            return True

        subprocess.run(["git", "-C", REPO, "commit", "-m", msg], check=False)

        for attempt in range(1, 4):
            jitter = random.uniform(1.5, 3.5)
            time.sleep(jitter)
            r_pull = subprocess.run(["git", "-C", REPO, "pull", "--rebase", "origin", "main"], capture_output=True, text=True)
            if r_pull.returncode == 0:
                r_push = subprocess.run(["git", "-C", REPO, "push", "origin", "main"], capture_output=True, text=True)
                if r_push.returncode == 0:
                    log(f"Successfully pushed update to origin/main on attempt {attempt}.")
                    return True
                else:
                    print(f"[GIT ERROR] Push failed attempt {attempt}/3 (code {r_push.returncode}): {r_push.stderr.strip()}", file=sys.stderr, flush=True)
                    subprocess.run(["git", "-C", REPO, "rebase", "--abort"], capture_output=True)
            else:
                print(f"[GIT ERROR] Pull rebase failed attempt {attempt}/3 (code {r_pull.returncode}): {r_pull.stderr.strip()}", file=sys.stderr, flush=True)
                subprocess.run(["git", "-C", REPO, "rebase", "--abort"], capture_output=True)
                # Fallback fetch and merge
                subprocess.run(["git", "-C", REPO, "fetch", "origin", "main"], capture_output=True)
                subprocess.run(["git", "-C", REPO, "merge", "--no-edit", "-X", "ours", "origin/main"], capture_output=True)
                r_push = subprocess.run(["git", "-C", REPO, "push", "origin", "main"], capture_output=True, text=True)
                if r_push.returncode == 0:
                    log(f"Successfully pushed update to origin/main on attempt {attempt} (via merge fallback).")
                    return True
                else:
                    print(f"[GIT ERROR] Push attempt {attempt}/3 failed after merge: {r_push.stderr.strip()}", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[GIT EXCEPTION] {e}", file=sys.stderr, flush=True)
    return False'''

HARVEST_GIT_SECTION_NEW = '''# ------------------------------------------------------------------------------
# GIT HELPER (FETCH, MERGE, COMMIT, PUSH WITH 15 RETRIES & BACKOFF)
# ------------------------------------------------------------------------------
def git_pull_repo():
    log("Pulling latest repo updates from origin/main...")
    subprocess.run(["git", "-C", REPO, "fetch", "origin", "main"], check=False)
    r = subprocess.run(["git", "-C", REPO, "merge", "--no-edit", "origin/main"], capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(["git", "-C", REPO, "merge", "--abort"], capture_output=True)
        log(f"Pull merge failed: {r.stderr.strip()}")
    else:
        log("Pulled successfully via merge.")

def git_sync_and_push(msg):
    try:
        subprocess.run(["git", "-C", REPO, "add", "-A"], check=False)
        st = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True)
        if not st.stdout.strip():
            return True
        c_res = subprocess.run(["git", "-C", REPO, "commit", "-m", msg], check=False)
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
                log(f"Successfully pushed update to origin/main on attempt {attempt}.")
                return True
            print(f"[GIT ERROR] Push failed attempt {attempt}/15: {p_res.stderr.strip()}", file=sys.stderr, flush=True)
            backoff = min(60, 2 ** attempt) * random.uniform(0.5, 1.5)
            time.sleep(backoff)
        return False
    except Exception as e:
        print(f"[GIT EXCEPTION] {e}", file=sys.stderr, flush=True)
        return False'''

def update_harvest(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Normalize CRLF / LF
    content = content.replace("\r\n", "\n")

    # Replace docstring rebase mention
    content = content.replace("Git helper with pull --rebase / add / commit / push with 3 retries, jitter, stderr printing, exit-code checks.",
                              "Git helper with fetch / merge / add / commit / push with 15 retries, backoff, stderr printing, exit-code checks.")

    # Replace git section
    old_git = HARVEST_GIT_SECTION_OLD.replace("\r\n", "\n")
    new_git = HARVEST_GIT_SECTION_NEW.replace("\r\n", "\n")
    if old_git not in content:
        raise ValueError(f"Could not find old git section in {path}")
    content = content.replace(old_git, new_git)

    # Update init in main()
    old_init = "    signal.signal(signal.SIGINT, handle_sig)\n    signal.signal(signal.SIGTERM, handle_sig)\n\n    while running:"
    new_init = "    signal.signal(signal.SIGINT, handle_sig)\n    signal.signal(signal.SIGTERM, handle_sig)\n\n    last_push_t = 0\n    last_pool_sig = (os.path.getmtime(POOL_FILE), os.path.getsize(POOL_FILE)) if os.path.exists(POOL_FILE) else None\n\n    while running:"
    if old_init not in content:
        raise ValueError(f"Could not find main init in {path}")
    content = content.replace(old_init, new_init)

    # Update commit & push call in main()
    old_push = '''        # 10. Commit & Push with 3 retries and jitter
        commit_msg = f"harvest: cycle #{cycle} +{added_to_pool} (pool: {pool_total:,})"
        git_sync_and_push(commit_msg)'''
    new_push = '''        # 10. Commit & Push only when harvest's own output file changed, at most once per 10 minutes
        now = time.time()
        cur_pool_sig = (os.path.getmtime(POOL_FILE), os.path.getsize(POOL_FILE)) if os.path.exists(POOL_FILE) else None
        if cur_pool_sig is not None and cur_pool_sig != last_pool_sig and (now - last_push_t >= 600):
            last_push_t = now
            commit_msg = f"harvest: cycle #{cycle} +{added_to_pool} (pool: {pool_total:,})"
            if git_sync_and_push(commit_msg):
                last_pool_sig = cur_pool_sig'''
    if old_push not in content:
        raise ValueError(f"Could not find old commit_msg push in {path}")
    content = content.replace(old_push, new_push)

    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)
    print(f"Updated {path}")

if __name__ == "__main__":
    shard_paths = ['kaggle/cl_shodan/run.py'] + [f'kaggle/cl_shodan_{i:02d}/run.py' for i in range(20)]
    for sp in shard_paths:
        full_p = os.path.join('D:\\DEpinFarm', sp)
        update_shard(full_p)

    harvest_p = os.path.join('D:\\DEpinFarm', 'kaggle/cl_harvest/run.py')
    update_harvest(harvest_p)
    print("ALL 22 FILES UPDATED SUCCESSFULLY.")
