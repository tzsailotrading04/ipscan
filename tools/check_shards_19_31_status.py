import os, subprocess, json

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

for tag, user, tok_file in shards:
    set_creds(user, tok_file)
    k_id = f'{user}/ipscan-cl-shodan-{tag}'
    res = subprocess.run(['kaggle', 'kernels', 'status', k_id], capture_output=True, text=True)
    st = 'UNKNOWN'
    for l in res.stdout.splitlines():
        if 'has status' in l:
            st = l.split('has status')[-1].replace('"', '').replace('KernelWorkerStatus.', '').strip()
    print(f'Shard {tag} ({user}): {st}')
