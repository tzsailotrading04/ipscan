import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("D:/DEpinFarm")
KAGGLE_DIR = Path(os.environ["USERPROFILE"]) / ".kaggle"
KAGGLE_JSON = KAGGLE_DIR / "kaggle.json"

def run_cmd(args, env=None):
    res = subprocess.run(args, capture_output=True, text=True, env=env)
    return res.stdout.strip(), res.stderr.strip(), res.returncode

def switch_account(account_name):
    src = ROOT / "accounts" / account_name / "kaggle.json"
    KAGGLE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, KAGGLE_JSON)
    with open(src, "r") as f:
        data = json.load(f)
    env = os.environ.copy()
    env["KAGGLE_USERNAME"] = data["username"]
    env["KAGGLE_KEY"] = data["key"]
    if "KAGGLE_API_TOKEN" in env:
        del env["KAGGLE_API_TOKEN"]
    return env

def main():
    print("=================== remruata ===================")
    env_rem = switch_account("remruata")
    out, err, _ = run_cmd(["kaggle", "kernels", "list", "-m", "--page-size", "10"], env=env_rem)
    print(out)
    if err:
        print("[stderr]", err)

    meta_01 = json.loads((ROOT / "kaggle/cl_shodan_01/kernel-metadata.json").read_text())
    id_01 = meta_01["id"]
    print(f"\nChecking status for {id_01}:")
    out, err, _ = run_cmd(["kaggle", "kernels", "status", id_01], env=env_rem)
    print(out)
    print(f"Fetching output for {id_01} into tmp/logs/now01:")
    out_dir_01 = ROOT / "tmp/logs/now01"
    out_dir_01.mkdir(parents=True, exist_ok=True)
    out, err, _ = run_cmd(["kaggle", "kernels", "output", id_01, "-p", str(out_dir_01)], env=env_rem)
    print(out)
    if err:
        print("[stderr]", err)

    print("\n=================== laldinthari ===================")
    env_lal = switch_account("laldinthari")
    out, err, _ = run_cmd(["kaggle", "kernels", "list", "-m", "--page-size", "10"], env=env_lal)
    print(out)
    if err:
        print("[stderr]", err)

    meta_11 = json.loads((ROOT / "kaggle/cl_shodan_11/kernel-metadata.json").read_text())
    id_11 = meta_11["id"]
    print(f"\nChecking status for {id_11}:")
    out, err, _ = run_cmd(["kaggle", "kernels", "status", id_11], env=env_lal)
    print(out)
    print(f"Fetching output for {id_11} into tmp/logs/now11:")
    out_dir_11 = ROOT / "tmp/logs/now11"
    out_dir_11.mkdir(parents=True, exist_ok=True)
    out, err, _ = run_cmd(["kaggle", "kernels", "output", id_11, "-p", str(out_dir_11)], env=env_lal)
    print(out)
    if err:
        print("[stderr]", err)

    print("\n=================== Downloaded Files in tmp/logs ===================")
    found = False
    for path in [out_dir_01, out_dir_11]:
        for f in path.rglob("*"):
            if f.is_file():
                found = True
                print(f"\n=== {f.relative_to(ROOT)} ({f.stat().st_size} bytes) ===")
                try:
                    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
                    print("\n".join(lines[-40:]))
                except Exception as e:
                    print(f"Error reading {f}: {e}")
    if not found:
        print("No files were produced by 'kaggle kernels output' (kernels are currently RUNNING).")

    print("\n=================== Live git branch status for sh01 and sh11 ===================")
    out, _, _ = run_cmd(["git", "show", "origin/out/sh01:ip/harvest/stage_01.txt"], env=os.environ)
    print("--- origin/out/sh01:ip/harvest/stage_01.txt (last 15 lines) ---")
    print("\n".join(out.splitlines()[-15:]))

    out, _, _ = run_cmd(["git", "show", "origin/out/sh11:ip/harvest/stage_11.txt"], env=os.environ)
    print("\n--- origin/out/sh11:ip/harvest/stage_11.txt (last 15 lines) ---")
    print("\n".join(out.splitlines()[-15:]))

if __name__ == "__main__":
    main()
