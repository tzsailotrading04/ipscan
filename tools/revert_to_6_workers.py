"""
tools/revert_to_6_workers.py
Reverts all 20 Kaggle shards back to 6 workers with batch size 1500.
Triggered if the 1-hour trial fails to beat 16 genuine/hr.
"""
import os
import subprocess
import sys

ROOT = r"D:\DEpinFarm"

def main():
    print("=" * 70)
    print("REVERTING FLEET TO 6 WORKERS (BATCH SIZE 1500)")
    print("=" * 70)

    # 1. Regenerate 6-worker code
    gen_script = os.path.join(ROOT, "tools", "generate_shards_12h_run.py")
    res = subprocess.run([sys.executable, gen_script], capture_output=True, text=True)
    print("Regeneration output:\n", res.stdout)
    if res.returncode != 0:
        print("Error regenerating code:", res.stderr)
        return

    # 2. Deploy all shards
    deploy_script = os.path.join(ROOT, "tools", "deploy_all_shards_clean.py")
    print("Deploying 6-worker configuration to Kaggle...")
    res_dep = subprocess.run([sys.executable, deploy_script], capture_output=True, text=True)
    print("Deployment output:\n", res_dep.stdout)

    print("Revert complete. All shards restored to 6 workers.")

if __name__ == "__main__":
    main()
