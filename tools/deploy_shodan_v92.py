import os
import json
import time
import subprocess
from kaggle.api.kaggle_api_extended import KaggleApi

ROOT = r"D:\DEpinFarm"
userprofile = os.environ.get("USERPROFILE", r"C:\Users\pc")
kaggle_bin = os.path.join(userprofile, r"AppData\Local\Python\pythoncore-3.14-64\Scripts\kaggle.exe")

def push_kernel_serialized(acct, folder, max_tries=5):
    token_p = os.path.join(ROOT, "kaggle", acct, "access_token")
    token = open(token_p).read().strip()
    env = os.environ.copy()
    env["KAGGLE_CONFIG_DIR"] = os.path.join(ROOT, "kaggle", acct)
    env["KAGGLE_API_TOKEN"] = token

    base_name = os.path.basename(folder)
    for attempt in range(1, max_tries + 1):
        r = subprocess.run([kaggle_bin, "kernels", "push", "-p", folder], env=env, capture_output=True, text=True)
        out = (r.stdout + "\n" + r.stderr).strip()
        if "successfully pushed" in out:
            print(f"pushed {base_name} successfully")
            return True
        elif "409" in out or "Conflict" in out:
            wait = 8 * attempt
            print(f"409 on {base_name} retry {attempt}/{max_tries} in {wait}s")
            time.sleep(wait)
        else:
            print(f"FAILED {base_name}: {out}")
            return False
            
    print(f"gave up on {base_name}")
    return False

def prepare_shard_folder(shard_idx, user):
    shard_tag = f"{shard_idx:02d}"
    k_dir = os.path.join(ROOT, "kaggle", f"cl_shodan_{shard_tag}")
    os.makedirs(k_dir, exist_ok=True)
    slug = f"ipscan-cl-shodan-{shard_tag}"

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

    template_p = os.path.join(ROOT, "kaggle", "cl_shodan", "run.py")
    with open(template_p, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace('shard_str = os.environ.get("SHARD_INDEX", os.environ.get("SLICE_IDX", ""))', f'shard_str = "{shard_idx}"')

    with open(os.path.join(k_dir, "run.py"), "w", encoding="utf-8") as f:
        f.write(content)

    return k_dir

if __name__ == "__main__":
    import sys
    shard_id = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    acct = sys.argv[2] if len(sys.argv) > 2 else "acct1"
    user = sys.argv[3] if len(sys.argv) > 3 else "lalthazualasailo"
    
    folder = prepare_shard_folder(shard_id, user)
    push_kernel_serialized(acct, folder)
