import json
import os
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path("D:/DEpinFarm")
KAGGLE_DIR = Path(os.environ["USERPROFILE"]) / ".kaggle"

FLEET = {
    "remruata": ['00', '01', '20', '21'],
    "lalthazualasailo": ['02', '03', '04', '05', '22'],
    "zomuanpuia": ['06', '07', '08', '09', '23'],
    "laldinthari": ['10', '11', '12', '13', '24'],
    "lalsangkima": ['15', '16', '17', '25', '26'],
    "spectatorlone": ['14', '18', '19', '27', '28'],
    "stephen34": ['29', '30', '31', '32', '33'],
}

def switch_account(account_name):
    src = ROOT / "accounts" / account_name / "kaggle.json"
    dest_json = KAGGLE_DIR / "kaggle.json"
    dest_token = KAGGLE_DIR / "access_token"
    shutil.copyfile(src, dest_json)
    data = json.loads(src.read_text(encoding="utf-8"))
    dest_token.write_text(data["key"], encoding="utf-8")
    env = os.environ.copy()
    env["KAGGLE_API_TOKEN"] = data["key"]
    env["KAGGLE_USERNAME"] = data["username"]
    env["KAGGLE_KEY"] = data["key"]
    return env

def delete_all():
    total_deleted = 0
    total_skipped = 0
    for acct, shards in FLEET.items():
        print(f"\n=================== Account: {acct} ===================")
        env = switch_account(acct)
        for s in shards:
            meta_path = ROOT / f"kaggle/cl_shodan_{s}/kernel-metadata.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            kernel_id = meta["id"]
            print(f"Deleting shard {s}: {kernel_id} ...", end=" ", flush=True)
            res = subprocess.run(["kaggle", "kernels", "delete", "-y", kernel_id], capture_output=True, text=True, env=env)
            output = (res.stdout + " " + res.stderr).strip()
            if "has been deleted" in output or "Kernel deleted" in output or res.returncode == 0:
                print("DELETED")
                total_deleted += 1
            elif "404" in output or "not found" in output.lower():
                print("NOT FOUND / ALREADY DELETED")
                total_skipped += 1
            else:
                print(f"OUTPUT: {output}")
                total_skipped += 1
            time.sleep(1)

    print(f"\nFinished: {total_deleted} deleted, {total_skipped} skipped/not found.")

if __name__ == "__main__":
    delete_all()
