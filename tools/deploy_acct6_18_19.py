import os
import subprocess
import time

ROOT = r"D:\DEpinFarm"
userprofile = os.environ.get("USERPROFILE", r"C:\Users\pc")
kaggle_bin = os.path.join(userprofile, r"AppData\Local\Python\pythoncore-3.14-64\Scripts\kaggle.exe")
tok = open(os.path.join(ROOT, "kaggle/acct6/access_token")).read().strip()
env = os.environ.copy()
env["KAGGLE_API_TOKEN"] = tok

for k in ["cl_shodan_18", "cl_shodan_19"]:
    slug = k.replace("_", "-")
    kid = f"spectatorlone/ipscan-{slug}"
    k_dir = os.path.join(ROOT, "kaggle", k)
    print(f"Deleting {kid}...")
    subprocess.run([kaggle_bin, "kernels", "delete", "-y", kid], env=env, capture_output=True, text=True, timeout=15)
    time.sleep(3)
    print(f"Pushing {kid}...")
    res = subprocess.run([kaggle_bin, "kernels", "push", "-p", k_dir], env=env, capture_output=True, text=True, timeout=30)
    print("STDOUT:", res.stdout.strip())
    print("STDERR:", res.stderr.strip())
    time.sleep(3)
    status = subprocess.run([kaggle_bin, "kernels", "status", kid], env=env, capture_output=True, text=True, timeout=15)
    print("STATUS:", status.stdout.strip())
