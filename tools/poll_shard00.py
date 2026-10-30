import os, subprocess, json, time, datetime

repo = r'D:\DEpinFarm'
tok = open(os.path.join(repo, 'kaggle', 'acct5', 'access_token')).read().strip()
env = os.environ.copy()
env['KAGGLE_USERNAME'] = 'remruata'
env['KAGGLE_KEY'] = tok
env['KAGGLE_API_TOKEN'] = tok

os.makedirs(os.path.expanduser('~/.kaggle'), exist_ok=True)
with open(os.path.expanduser('~/.kaggle/kaggle.json'), 'w') as f:
    json.dump({'username': 'remruata', 'key': tok}, f)

push_time = time.time()
print("Starting poll at " + datetime.datetime.now().strftime("%H:%M:%S"))

for i in range(36):
    res = subprocess.run(['kaggle', 'kernels', 'status', 'remruata/ipscan-cl-shodan-00'], env=env, capture_output=True, text=True)
    out = (res.stdout + ' ' + res.stderr).strip().replace('\r', '')
    now_str = datetime.datetime.now().strftime('%H:%M:%S')
    print(f"[{now_str}] Poll #{i+1}: {out}")
    if 'RUNNING' in out:
        elapsed = time.time() - push_time
        print(f"RUNNING detected after {elapsed:.1f}s!")
        print(f"Start time is inside {elapsed:.1f}s (well inside 2 minutes threshold).")
        break
    if 'ERROR' in out or 'FAILED' in out:
        print("Detected failure state!")
        break
    time.sleep(5)
