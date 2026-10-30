import os, subprocess, json, sys

repo = r'D:\DEpinFarm'

# Stop flag
with open(os.path.join(repo, 'work', 'STOP_SHODAN'), 'w') as f:
    f.write('STOP')
print("Placed work/STOP_SHODAN flag.")

accounts = {
    'acct0': ('stephen34', [29, 30, 31, 32, 33]),
    'acct1': ('lalthazualasailo', [2, 3, 4, 5, 22]),
    'acct2': ('zomuanpuia', [6, 7, 8, 9, 23]),
    'acct3': ('laldinthari', [10, 11, 12, 13, 24]),
    'acct4': ('lalsangkima', [15, 16, 17, 25, 26]),
    'acct5': ('remruata', [0, 1, 20]),
    'acct6': ('spectatorlone', [14, 18, 19, 27, 28]),
}

deleted = []
already_none = []

for acct_folder, (username, shards) in accounts.items():
    tok_path = os.path.join(repo, 'kaggle', acct_folder, 'access_token')
    if not os.path.exists(tok_path):
        continue
    tok = open(tok_path).read().strip()
    env = os.environ.copy()
    env['KAGGLE_USERNAME'] = username
    env['KAGGLE_KEY'] = tok
    env['KAGGLE_API_TOKEN'] = tok

    with open(os.path.expanduser('~/.kaggle/kaggle.json'), 'w') as f:
        json.dump({'username': username, 'key': tok}, f)

    for s in shards:
        slug = f'{username}/ipscan-cl-shodan-{s:02d}'
        st_res = subprocess.run(['kaggle', 'kernels', 'status', slug], env=env, capture_output=True, text=True)
        st_out = (st_res.stdout + ' ' + st_res.stderr).strip().replace('\r', ' ')
        
        if '404' in st_out or 'not found' in st_out.lower() or 'permission' in st_out.lower():
            already_none.append((s, username))
            continue
        
        print(f"Cancelling/Deleting shard {s:02d} ({slug}) [Status: {st_out.splitlines()[-1]}]...")
        del_res = subprocess.run(['kaggle', 'kernels', 'delete', '-y', slug], env=env, capture_output=True, text=True)
        del_out = (del_res.stdout + ' ' + del_res.stderr).strip().replace('\r', ' ')
        print(f"  -> Result: {del_out.splitlines()[-1]}")
        deleted.append((s, username))

print("\n=== SUMMARY ===")
print(f"Total shards cancelled/deleted: {len(deleted)}")
for s, u in deleted:
    print(f"  Shard {s:02d} ({u}) CANCELLED/DELETED")
print(f"Total already not running: {len(already_none)}")
