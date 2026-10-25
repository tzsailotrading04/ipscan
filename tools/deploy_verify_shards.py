import os
import json
import time
import subprocess

ROOT = r"D:\DEpinFarm"
userprofile = os.environ.get("USERPROFILE", r"C:\Users\pc")
kaggle_bin = os.path.join(userprofile, r"AppData\Local\Python\pythoncore-3.14-64\Scripts\kaggle.exe")

VERIFY_FLEET = [
    (0, "acct1", "lalthazualasailo", "ipscan-cl-verify-0"),
    (1, "acct2", "zomuanpuia", "ipscan-cl-verify-1"),
    (2, "acct3", "laldinthari", "ipscan-cl-verify-2"),
    (3, "acct4", "lalsangkima", "ipscan-cl-verify-3"),
]

def deploy_verify_shard(shard_id, acct, user, slug, total_shards=4):
    print(f"\nDeploying Verify Shard {shard_id}/{total_shards} -> {acct} ({user}/{slug})...", flush=True)
    k_dir = os.path.join(ROOT, "kaggle", f"cl_verify_{shard_id}")
    os.makedirs(k_dir, exist_ok=True)

    meta = {
        "id": f"{user}/{slug}",
        "title": slug,
        "code_file": "run.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": False,
        "enable_internet": True,
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": []
    }
    with open(os.path.join(k_dir, "kernel-metadata.json"), "w") as f:
        json.dump(meta, f, indent=2)

    # Read runner template
    template_p = os.path.join(ROOT, "kaggle", "cl_verify_shard", "run.py")
    with open(template_p, "r", encoding="utf-8") as f:
        content = f.read()

    # Inject explicit shard definition
    content = content.replace('VERIFY_SHARD_ID = int(os.environ.get("VERIFY_SHARD_ID", sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].isdigit() else "0"))', f'VERIFY_SHARD_ID = {shard_id}')
    content = content.replace('VERIFY_SHARD_TOTAL = int(os.environ.get("VERIFY_SHARD_TOTAL", sys.argv[2] if len(sys.argv) > 2 and sys.argv[2].isdigit() else "4"))', f'VERIFY_SHARD_TOTAL = {total_shards}')

    with open(os.path.join(k_dir, "run.py"), "w", encoding="utf-8") as f:
        f.write(content)

    token = open(os.path.join(ROOT, "kaggle", acct, "access_token")).read().strip()
    env = os.environ.copy()
    env["KAGGLE_CONFIG_DIR"] = os.path.join(ROOT, "kaggle", acct)
    env["KAGGLE_API_TOKEN"] = token

    # Check and delete existing if present
    subprocess.run([kaggle_bin, "kernels", "delete", "-y", f"{user}/{slug}"], env=env, capture_output=True, text=True)
    time.sleep(3)

    for attempt in range(1, 6):
        r = subprocess.run([kaggle_bin, "kernels", "push", "-p", k_dir], env=env, capture_output=True, text=True)
        out = (r.stdout + "\n" + r.stderr).strip()
        if "successfully pushed" in out:
            print(f"  Result: OK | Pushed {slug}")
            return True
        elif "409" in out or "Conflict" in out:
            wait = 8 * attempt
            print(f"  409 Conflict retry {attempt}/5 in {wait}s...")
            time.sleep(wait)
        else:
            print(f"  Result: FAIL | {out}")
            time.sleep(3)
    return False

if __name__ == "__main__":
    for item in VERIFY_FLEET:
        deploy_verify_shard(*item)
        time.sleep(3)
