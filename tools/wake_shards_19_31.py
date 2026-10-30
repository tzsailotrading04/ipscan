import os, subprocess, json, time

repo = r'D:\DEpinFarm'
KAGGLE_JSON = os.path.expanduser('~/.kaggle/kaggle.json')

shards = [
    ('19', 'spectatorlone', os.path.join(repo, 'kaggle', 'acct6', 'access_token')),
    ('31', 'stephen34', os.path.join(repo, 'kaggle', 'stephen34', 'access_token'))
]

def set_creds(user, token_file):
    with open(token_file) as f: tok = f.read().strip()
    os.environ['KAGGLE_API_TOKEN'] = tok
    os.environ['KAGGLE_USERNAME'] = user
    os.environ['KAGGLE_KEY'] = tok
    with open(KAGGLE_JSON, 'w') as f: json.dump({'username': user, 'key': tok}, f)

print('=== STATUS BEFORE REPUSH ===')
for tag, user, tok_file in shards:
    set_creds(user, tok_file)
    k_id = f'{user}/ipscan-cl-shodan-{tag}'
    res = subprocess.run(['kaggle', 'kernels', 'status', k_id], capture_output=True, text=True)
    st = 'UNKNOWN'
    for l in res.stdout.splitlines():
        if 'has status' in l:
            st = l.split('has status')[-1].replace('"', '').replace('KernelWorkerStatus.', '').strip()
    print(f'Shard {tag} ({user}): {st}')

print('\n=== REPUSHING SHARDS ===')
for tag, user, tok_file in shards:
    set_creds(user, tok_file)
    shard_dir = os.path.join(repo, 'kaggle', f'cl_shodan_{tag}')
    k_id = f'{user}/ipscan-cl-shodan-{tag}'
    pushed = False
    for att in range(1, 4):
        res = subprocess.run(['kaggle', 'kernels', 'push', '-p', shard_dir], capture_output=True, text=True)
        out = (res.stdout + '\n' + res.stderr).strip()
        if 'successfully pushed' in out or 'updated' in out or 'notebook was successfully pushed' in out:
            pushed = True
            print(f'Shard {tag} pushed successfully on attempt {att}')
            break
        elif 'Maximum batch CPU session count of 5 reached' in out:
            print(f'Shard {tag}: cap reached, deleting container to drain and retrying...')
            subprocess.run(['kaggle', 'kernels', 'delete', '-y', k_id], capture_output=True, text=True)
            time.sleep(2)
        else:
            print(f'Attempt {att} failed: {out}')
            time.sleep(2)

print('\n=== STATUS AFTER REPUSH ===')
time.sleep(3)
for tag, user, tok_file in shards:
    set_creds(user, tok_file)
    k_id = f'{user}/ipscan-cl-shodan-{tag}'
    res = subprocess.run(['kaggle', 'kernels', 'status', k_id], capture_output=True, text=True)
    st = 'UNKNOWN'
    for l in res.stdout.splitlines():
        if 'has status' in l:
            st = l.split('has status')[-1].replace('"', '').replace('KernelWorkerStatus.', '').strip()
    print(f'Shard {tag} ({user}): {st}')
