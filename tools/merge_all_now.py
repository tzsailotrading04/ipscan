import os, subprocess, glob, time

REPO = r"D:\DEpinFarm"

print("Fetching all remote out/sh* branches...")
subprocess.run(['git', '-C', REPO, 'fetch', 'origin', '+refs/heads/out/sh*:refs/remotes/origin/out/sh*', '--prune'], check=False)

res = subprocess.run(['git', '-C', REPO, 'branch', '-r', '--list', 'origin/out/sh*'], capture_output=True, text=True)
branches = [b.strip() for b in res.stdout.splitlines() if b.strip()]
print(f"Total out/sh* branches found on remote: {len(branches)}")

for rb in branches:
    bname = rb.replace("origin/", "")
    tag = bname.replace("out/sh", "")
    cmd = [
        'git', '-C', REPO, 'checkout', rb, '--',
        f'ip/harvest/verified_alive_part_{tag}.txt',
        f'ip/harvest/verified_alive_part_{tag}_w0.txt',
        f'ip/harvest/verified_alive_part_{tag}_w1.txt',
        f'ip/harvest/stage_{tag}.txt'
    ]
    subprocess.run(cmd, capture_output=True, check=False)

print("Checked out files from all available branches.")
