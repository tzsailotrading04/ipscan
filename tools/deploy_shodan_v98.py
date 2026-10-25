import os, sys, time, shutil, subprocess, tempfile

ROOT = r"D:\DEpinFarm"
ACC_DIR = os.path.join(ROOT, "kaggle")
SRC = os.path.join(ROOT, "kaggle", "cl_shodan")
OWNER = "tzsailotrading04"

SHARD_ACCT = {
    0: "acct5", 1: "acct5",
    2: "acct1", 3: "acct1", 4: "acct1", 5: "acct1",
    6: "acct2", 7: "acct2", 8: "acct2", 9: "acct2",
    10: "acct3", 11: "acct3", 12: "acct3", 13: "acct3",
    14: "acct4", 15: "acct4", 16: "acct4", 17: "acct4",
    18: "acct6", 19: "acct6",
}

TMP = os.path.join(tempfile.gettempdir(), "shodan_v98")

META = """{{
  "id": "{owner}/ipscan-cl-shodan-{tag}",
  "title": "ipscan-cl-shodan-{tag}",
  "code_file": "run.py",
  "language": "python",
  "kernel_type": "script",
  "is_private": true,
  "enable_gpu": false,
  "enable_internet": true,
  "dataset_sources": [],
  "competition_sources": [],
  "kernel_sources": [],
  "model_sources": []
}}"""


def push_one(idx):
    tag = f"{idx:02d}"
    acct = SHARD_ACCT[idx]
    d = os.path.join(TMP, f"shard_{tag}")
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d)

    with open(os.path.join(SRC, "run.py"), "r", encoding="utf-8") as f:
        code = f.read()

    if '    shard_str = "0"' not in code:
        print(f"  !! marker not found in run.py for shard {tag}")
    code = code.replace('    shard_str = "0"', f'    shard_str = "{tag}"')

    with open(os.path.join(d, "run.py"), "w", encoding="utf-8") as f:
        f.write(code)
    with open(os.path.join(d, "kernel-metadata.json"), "w", encoding="utf-8") as f:
        f.write(META.format(owner=OWNER, tag=tag))

    tok = open(os.path.join(ACC_DIR, acct, "access_token")).read().strip()
    env = os.environ.copy()
    env["KAGGLE_API_TOKEN"] = tok
    env["KAGGLE_KEY"] = tok
    env["KAGGLE_CONFIG_DIR"] = os.path.join(ACC_DIR, acct)

    for attempt in range(1, 6):
        r = subprocess.run(
            [sys.executable, "-m", "kaggle", "kernels", "push", "-p", d],
            capture_output=True, text=True, env=env,
        )
        out = r.stdout + r.stderr
        if r.returncode == 0:
            print(f"shard {tag} [{acct}] PUSH_OK")
            return True
        if "409" in out or "Conflict" in out:
            wait = 3 * attempt
            print(f"shard {tag} [{acct}] 409, retry in {wait}s")
            time.sleep(wait)
            continue
        print(f"shard {tag} [{acct}] FAIL: {out.strip()[:200]}")
        return False
    print(f"shard {tag} [{acct}] FAILED after 5 attempts")
    return False


def main():
    os.makedirs(TMP, exist_ok=True)
    order = list(range(20))
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        order = [int(sys.argv[1])]
    ok = 0
    for i in order:
        if push_one(i):
            ok += 1
        time.sleep(3)
    print(f"\nPUSHED {ok}/{len(order)}")


if __name__ == "__main__":
    main()
