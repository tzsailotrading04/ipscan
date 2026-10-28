"""
retarget_all_shards_hosting.py
1. Updates load_strided_subnets in all 20 cl_shodan_XX/run.py to load hosting_subnets.txt
2. Resets shodan_progress_v98_XX.txt to 0 for all 20 shards
3. Commits and pushes changes to origin/main
4. Deploys/pushes all 20 shards to Kaggle in waves of 4
"""
import glob
import json
import os
import py_compile
import subprocess
import time

ROOT = r"D:\DEpinFarm"
userprofile = os.environ.get("USERPROFILE", r"C:\Users\pc")
kaggle_bin = os.path.join(userprofile, r"AppData\Local\Python\pythoncore-3.14-64\Scripts\kaggle.exe")

SHARDS = [
    ("acct5", ["cl_shodan_00", "cl_shodan_01"]),
    ("acct1", ["cl_shodan_02", "cl_shodan_03", "cl_shodan_04", "cl_shodan_05"]),
    ("acct2", ["cl_shodan_06", "cl_shodan_07", "cl_shodan_08", "cl_shodan_09"]),
    ("acct3", ["cl_shodan_10", "cl_shodan_11", "cl_shodan_12", "cl_shodan_13"]),
    ("acct4", ["cl_shodan_15", "cl_shodan_16", "cl_shodan_17"]),
    ("acct6", ["cl_shodan_14", "cl_shodan_18", "cl_shodan_19"]),
]

NEW_LOAD_SUBNETS = '''def load_strided_subnets():
    log(f"Loading hosting ASN subnets for shard {SHARD_TAG}...")
    t0 = time.time()
    subnets_file = os.path.join(REPO, "data", "hosting_subnets.txt")
    if not os.path.exists(subnets_file):
        subnets_file = os.path.join(os.path.dirname(__file__), "..", "..", "data", "hosting_subnets.txt")
    subnets = []
    with open(subnets_file, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx % NUM_SHARDS == SHARD_IDX:
                subnets.append(line.strip())
    t1 = time.time()
    log(f"Loaded {len(subnets):,} hosting subnets ({len(subnets)*256:,} IPs) for shard {SHARD_TAG} in {t1-t0:.2f}s")
    log(f"STRIDE_CHECK first={subnets[0] if subnets else 'NONE'} last={subnets[-1] if subnets else 'NONE'}")
    return subnets
'''

def update_code():
    print("Updating load_strided_subnets() across all 20 shard files...")
    for idx in range(20):
        tag = f"{idx:02d}"
        path = os.path.join(ROOT, "kaggle", f"cl_shodan_{tag}", "run.py")
        with open(path, "r", encoding="utf-8") as f:
            code = f.read()

        s_marker = "def load_strided_subnets():"
        e_marker = "PROXY_PORTS = {"
        s_idx = code.find(s_marker)
        e_idx = code.find(e_marker)
        if s_idx == -1 or e_idx == -1:
            raise ValueError(f"Markers not found in {path}")

        new_code = code[:s_idx] + NEW_LOAD_SUBNETS + "\n\n" + code[e_idx:]
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_code)
        py_compile.compile(path, doraise=True)
        print(f"  * Updated and verified cl_shodan_{tag}/run.py")

def reset_cursors():
    print("\nResetting progress cursors for all 20 shards to 0...")
    for idx in range(20):
        tag = f"{idx:02d}"
        prog_path = os.path.join(ROOT, "ip", "harvest", f"shodan_progress_v98_{tag}.txt")
        stats_path = os.path.join(ROOT, "ip", "harvest", f"shodan_stats_v98_{tag}.txt")
        with open(prog_path, "w", encoding="utf-8") as f:
            f.write("0\nchunk=1\n")
        if os.path.exists(stats_path):
            with open(stats_path, "w", encoding="utf-8") as f:
                f.write(f"engine=v98.163\nshard={tag}\noffset=0\ntotal=20909824\nchunk=1\n")
        print(f"  * Reset shard_{tag} cursor to offset=0")

def git_commit_push():
    print("\nCommitting and pushing retargeted shards and reset cursors to origin/main...")
    subprocess.run(["git", "-C", ROOT, "add", "kaggle/cl_shodan_*/run.py", "ip/harvest/shodan_progress_v98_*.txt", "ip/harvest/shodan_stats_v98_*.txt", "data/hosting_subnets.txt"], check=False)
    r_commit = subprocess.run(["git", "-C", ROOT, "commit", "-m", "feat(fleet): retarget all 20 shards to 418M hosting IPs with strict probe (offset=0, no overlap)"], capture_output=True, text=True)
    print("Commit output:", r_commit.stdout.strip() if r_commit.stdout else "Nothing to commit or committed")
    
    for attempt in range(1, 5):
        subprocess.run(["git", "-C", ROOT, "pull", "--rebase", "origin", "main"], capture_output=True)
        r_push = subprocess.run(["git", "-C", ROOT, "push", "origin", "main"], capture_output=True, text=True)
        if r_push.returncode == 0:
            print("Successfully pushed to origin/main!")
            return True
        print(f"Push attempt {attempt} failed, retrying...")
        time.sleep(3)
    return False

def deploy_shards_staggered():
    print("\nDeploying all 20 shards to Kaggle in staggered waves of 4...")
    all_shards = []
    for acct, klist in SHARDS:
        for k in klist:
            all_shards.append((acct, k))

    batch_size = 4
    waves = [all_shards[i:i + batch_size] for i in range(0, len(all_shards), batch_size)]

    for w_idx, wave in enumerate(waves, 1):
        wave_str = ", ".join(f"{k}({acct})" for acct, k in wave)
        print(f"\n--- Wave {w_idx}/{len(waves)}: Launching [{wave_str}] ---")
        for acct, k in wave:
            tok = open(os.path.join(ROOT, "kaggle", acct, "access_token")).read().strip()
            env = os.environ.copy()
            env["KAGGLE_API_TOKEN"] = tok

            meta_path = os.path.join(ROOT, "kaggle", k, "kernel-metadata.json")
            meta = json.load(open(meta_path))
            kid = meta["id"]

            kdir = os.path.join(ROOT, "kaggle", k)
            print(f"  [{k}] Pushing to Kaggle ({kid})...", end="", flush=True)
            res = subprocess.run([kaggle_bin, "kernels", "push", "-p", kdir], env=env, capture_output=True, text=True)
            if "successfully" in res.stdout.lower() or "version" in res.stdout.lower():
                print(" OK (Pushed!)")
            else:
                print(f" WARN: {res.stdout.strip()} {res.stderr.strip()}")
            time.sleep(2)

        if w_idx < len(waves):
            print("Waiting 10s before next wave to stagger load...")
            time.sleep(10)

    print("\n=== ALL 20 SHARDS RETARGETED AND LAUNCHED ON HOSTING LIST ===")

def main():
    update_code()
    reset_cursors()
    git_commit_push()
    deploy_shards_staggered()

if __name__ == "__main__":
    main()
