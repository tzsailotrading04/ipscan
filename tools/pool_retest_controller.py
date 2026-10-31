#!/usr/bin/env python3
"""
Pool Retest Controller - Full Pool Verification via Kaggle Fleet
1. Partitions ip/harvest/real_pool.txt into chunks inside ip/harvest/queue/.
2. Pushes queue batches to origin/main.
3. Pushes/triggers all 34 Kaggle shards across all 7 accounts.
4. Monitors remote out/sh* branches and merges verified alive and failed parts.
5. Applies the two-strike rule:
   - Passes: confirmed alive, healed from cache/pool_suspect.txt, retained in real_pool.txt.
   - Fails (Strike 1): marked in cache/pool_suspect.txt, stays in pool.
   - Fails (Strike 2): retired to cache/pool_dead.txt, purged from real_pool.txt.
6. Reports total tested, passed, failed, and pool counts before/after.
"""
import os
import sys
import glob
import json
import time
import shutil
import subprocess
import re

REPO_ROOT = r"D:\DEpinFarm"
POOL_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool.txt")
BACKUP_FILE = os.path.join(REPO_ROOT, "ip", "harvest", "real_pool_pre_kaggle_reverify.txt")
SUSPECT_FILE = os.path.join(REPO_ROOT, "cache", "pool_suspect.txt")
DEAD_FILE = os.path.join(REPO_ROOT, "cache", "pool_dead.txt")
QUEUE_DIR = os.path.join(REPO_ROOT, "ip", "harvest", "queue")
ARCHIVE_DIR = os.path.join(REPO_ROOT, "cache", "queue_archive")

def run(cmd, check=True):
    res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, errors="replace")
    if check and res.returncode != 0:
        print(f"[CMD ERROR] {cmd}: {res.stderr}")
    return res.stdout.strip(), res.stderr.strip(), res.returncode

def load_pool():
    pool = {}
    if os.path.exists(POOL_FILE):
        with open(POOL_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                raw = line.strip()
                if raw:
                    ep = raw.split("\t")[0].split()[0]
                    pool[ep] = raw
    return pool

def load_suspects():
    suspects = set()
    if os.path.exists(SUSPECT_FILE):
        with open(SUSPECT_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                raw = line.strip()
                if raw:
                    suspects.add(raw.split("\t")[0].split()[0])
    return suspects

def build_queue_chunks(chunk_size=3600):
    os.makedirs(QUEUE_DIR, exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    # Archive existing queue files
    for qf in glob.glob(os.path.join(QUEUE_DIR, "q_*.txt")):
        dst = os.path.join(ARCHIVE_DIR, os.path.basename(qf))
        shutil.move(qf, dst)
        print(f"Archived existing queue file {os.path.basename(qf)} -> cache/queue_archive/")

    pool = load_pool()
    endpoints = list(pool.keys())
    total_eps = len(endpoints)
    print(f"Loaded {total_eps} unique endpoints from real_pool.txt to test.")

    ts = int(time.time())
    chunk_files = []
    for i in range(0, total_eps, chunk_size):
        chunk = endpoints[i:i + chunk_size]
        chunk_idx = (i // chunk_size) + 1
        fname = f"q_reverify_pool_{ts}_{chunk_idx:02d}.txt"
        fpath = os.path.join(QUEUE_DIR, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            for ep in chunk:
                f.write(ep + "\n")
        chunk_files.append((fname, len(chunk)))
        print(f"Created queue chunk: {fname} with {len(chunk)} endpoints.")

    # Commit and push queue files
    run(["git", "add", "ip/harvest/queue/"])
    run(["git", "commit", "-m", f"feat(harvest): add {len(chunk_files)} reverify queue chunks ({total_eps} endpoints)"])
    out, err, code = run(["git", "push", "origin", "main"])
    if code == 0:
        print(f"Successfully pushed {len(chunk_files)} queue chunks to origin/main.")
    else:
        print(f"Warning: git push failed: {err or out}")

    return chunk_files, total_eps

def push_fleet():
    repush_script = os.path.join(REPO_ROOT, "tools", "repush_all_34.py")
    print("\nTriggering all 34 shards via repush_all_34.py...")
    res = subprocess.run([sys.executable, repush_script], cwd=REPO_ROOT, capture_output=True, text=True, errors="replace")
    print(res.stdout)
    if res.stderr:
        print(res.stderr)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--build-queue":
        build_queue_chunks()
    elif len(sys.argv) > 1 and sys.argv[1] == "--push-fleet":
        push_fleet()
    else:
        print("Usage: python tools/pool_retest_controller.py [--build-queue | --push-fleet]")
