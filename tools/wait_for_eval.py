import time
import subprocess
import os
import sys

REPO_ROOT = r"D:\DEpinFarm"
OUT_DIR = os.path.join(REPO_ROOT, "work", "hosting_eval_output")
os.makedirs(OUT_DIR, exist_ok=True)
REF = "spectatorlone/test-hosting-eval-20k"

def main():
    print(f"Monitoring {REF} until complete...", flush=True)
    t0 = time.time()
    while True:
        res = subprocess.run(["kaggle", "kernels", "status", REF], capture_output=True, text=True)
        status_line = res.stdout.strip()
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Status: {status_line} (elapsed: {time.time()-t0:.0f}s)", flush=True)
        
        if "COMPLETE" in status_line:
            print("Kernel completed successfully! Downloading output...", flush=True)
            dl_res = subprocess.run(["kaggle", "kernels", "output", REF, "-p", OUT_DIR], capture_output=True, text=True)
            print(dl_res.stdout)
            print(dl_res.stderr)
            break
        elif "ERROR" in status_line or "FAILED" in status_line or "CANCEL" in status_line:
            print(f"Kernel ended with error: {status_line}", flush=True)
            subprocess.run(["kaggle", "kernels", "output", REF, "-p", OUT_DIR], capture_output=True, text=True)
            break
        
        # Check every 30 seconds
        time.sleep(30)

    # Print log file if exists
    for f in os.listdir(OUT_DIR):
        print(f"Output file: {f}")
        fpath = os.path.join(OUT_DIR, f)
        if f.endswith(".log") or f.endswith(".txt") or f.endswith(".json"):
            print("--- Content ---")
            with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
                print(fp.read())
            print("---------------")

if __name__ == "__main__":
    main()
