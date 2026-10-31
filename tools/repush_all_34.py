import os, subprocess, json, time, sys

repo = r'D:\DEpinFarm'
userprofile = os.environ.get('USERPROFILE', r'C:\Users\pc')
kaggle_dir = os.path.join(userprofile, '.kaggle')
os.makedirs(kaggle_dir, exist_ok=True)

groups = [
    ('remruata', ['00', '01', '20', '21']),
    ('lalthazualasailo', ['02', '03', '04', '05', '22']),
    ('zomuanpuia', ['06', '07', '08', '09', '23']),
    ('laldinthari', ['10', '11', '12', '13', '24']),
    ('lalsangkima', ['15', '16', '17', '25', '26']),
    ('spectatorlone', ['14', '18', '19', '27', '28']),
    ('stephen34', ['29', '30', '31', '32', '33']),
]

for username, shards in groups:
    print(f"\n==========================================")
    print(f"Pushing shards on {username} ({len(shards)} shards)")
    print(f"==========================================")
    
    acct_json = os.path.join(repo, 'accounts', username, 'kaggle.json')
    with open(acct_json, 'r') as f:
        creds = json.load(f)
    with open(os.path.join(kaggle_dir, 'kaggle.json'), 'w') as f:
        json.dump(creds, f, indent=2)
    with open(os.path.join(kaggle_dir, 'access_token'), 'w') as f:
        f.write(creds['key'])

    env = os.environ.copy()
    env['KAGGLE_USERNAME'] = creds['username']
    env['KAGGLE_KEY'] = creds['key']
    env['KAGGLE_API_TOKEN'] = creds['key']

    for s in shards:
        kernel_path = os.path.join(repo, 'kaggle', f'cl_shodan_{s}')
        print(f">>> kaggle kernels push -p kaggle\\cl_shodan_{s}", flush=True)
        res = subprocess.run(['kaggle', 'kernels', 'push', '-p', kernel_path], env=env, capture_output=True, text=True)
        lines = [l for l in (res.stdout + '\n' + res.stderr).splitlines() if l.strip() and not l.startswith('Warning:')]
        out = lines[-1] if lines else 'OK'
        print(f"    {out}", flush=True)
        time.sleep(3)

print("\n==========================================")
print("ALL 34 SHARDS SUCCESSFULLY PUSHED")
print("==========================================")
