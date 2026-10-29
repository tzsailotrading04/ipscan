#!/usr/bin/env python3
"""
Apply ungate push to master and all 34 shards.
Replaces the push gate with:
    now = time.time()
    cur_sig = (os.path.getmtime(shard_part), os.path.getsize(shard_part)) if os.path.exists(shard_part) else None
    part_changed = (cur_sig is not None and cur_sig != last_shard_sig)
    time_elapsed = (now - last_push_t >= 300)

    if part_changed or time_elapsed:
        last_push_t = now
        commit_msg = f"{ENGINE_VER} shard_{SHARD_TAG}: offset={total_offset} cands={total_cands} random_loop"
        if git_sync_and_push(commit_msg):
            last_shard_sig = cur_sig
"""
import glob
import os

OLD_BLOCK = """        # Push to git only when this shard's own output file changed, at most once per 10 minutes
        now = time.time()
        if now - last_push_t >= 600:
            cur_sig = (os.path.getmtime(shard_part), os.path.getsize(shard_part)) if os.path.exists(shard_part) else None
            if cur_sig is not None and cur_sig != last_shard_sig:
                last_push_t = now
                commit_msg = f"{ENGINE_VER} shard_{SHARD_TAG}: offset={total_offset} cands={total_cands} random_loop"
                if git_sync_and_push(commit_msg):
                    last_shard_sig = cur_sig"""

NEW_BLOCK = """        # Push to git when part file changed OR 300 seconds have passed since last push
        now = time.time()
        cur_sig = (os.path.getmtime(shard_part), os.path.getsize(shard_part)) if os.path.exists(shard_part) else None
        part_changed = (cur_sig is not None and cur_sig != last_shard_sig)
        time_elapsed = (now - last_push_t >= 300)

        if part_changed or time_elapsed:
            last_push_t = now
            commit_msg = f"{ENGINE_VER} shard_{SHARD_TAG}: offset={total_offset} cands={total_cands} random_loop"
            if git_sync_and_push(commit_msg):
                last_shard_sig = cur_sig"""

def update_file(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Normalize CRLF to LF for matching
    has_crlf = "\r\n" in content
    content_norm = content.replace("\r\n", "\n")

    if OLD_BLOCK in content_norm:
        content_norm = content_norm.replace(OLD_BLOCK, NEW_BLOCK)
        if has_crlf:
            content_norm = content_norm.replace("\n", "\r\n")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(content_norm)
        return True
    elif NEW_BLOCK in content_norm:
        return True
    return False

def check_file(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().replace("\r\n", "\n")
    old_present = OLD_BLOCK in content
    new_present = NEW_BLOCK in content
    return old_present, new_present

if __name__ == "__main__":
    # Master
    master = r"D:\DEpinFarm\kaggle\cl_shodan\run.py"
    res_master = update_file(master)
    print(f"Master {master}: updated={res_master}")

    # Shards 00..33
    shards = sorted(glob.glob(r"D:\DEpinFarm\kaggle\cl_shodan_*\run.py"))
    for s in shards:
        update_file(s)

    print(f"{'file':<35} | {'old condition present':<23} | {'new timer present':<20}")
    print("-" * 84)
    all_ok = True
    for s in shards:
        rel = os.path.relpath(s, r"D:\DEpinFarm")
        old_p, new_p = check_file(s)
        old_str = "yes" if old_p else "no"
        new_str = "yes" if new_p else "no"
        print(f"{rel:<35} | {old_str:<23} | {new_str:<20}")
        if old_p or not new_p:
            all_ok = False

    if all_ok:
        print("\nALL 34 SHARDS UPDATED SUCCESSFULLY")
    else:
        print("\nSOME SHARDS FAILED TO UPDATE")
