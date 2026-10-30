import os, glob, subprocess, json, time

repo = r'D:\DEpinFarm'
pool_file = os.path.join(repo, 'ip', 'harvest', 'real_pool.txt')
dead_file = os.path.join(repo, 'cache', 'pool_dead.txt')
suspect_file = os.path.join(repo, 'cache', 'pool_suspect.txt')
fleet_log = os.path.join(repo, 'work', 'FLEET_CYCLE.txt')
morning_file = os.path.join(repo, 'work', 'MORNING.txt')

def count_lines(path):
    if not os.path.exists(path): return 0
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return sum(1 for line in f if line.strip())

pool_size = count_lines(pool_file)
dead_size = count_lines(dead_file)
suspect_size = count_lines(suspect_file)
part_files = glob.glob(os.path.join(repo, 'ip', 'harvest', 'verified_alive_part_*.txt'))
part_files_count = len(part_files)

fleet_tail = []
if os.path.exists(fleet_log):
    with open(fleet_log, 'r', encoding='utf-8', errors='ignore') as f:
        fleet_tail = [l.strip() for l in f.readlines() if l.strip()][-5:]

# Status of shards 19 and 31
KAGGLE_JSON = os.path.expanduser('~/.kaggle/kaggle.json')
shards = [
    ('19', 'spectatorlone', os.path.join(repo, 'kaggle', 'acct6', 'access_token')),
    ('31', 'stephen34', os.path.join(repo, 'kaggle', 'stephen34', 'access_token'))
]

shard_statuses = {}
for tag, user, tok_file in shards:
    with open(tok_file) as f: tok = f.read().strip()
    os.environ['KAGGLE_API_TOKEN'] = tok
    os.environ['KAGGLE_USERNAME'] = user
    os.environ['KAGGLE_KEY'] = tok
    with open(KAGGLE_JSON, 'w') as f: json.dump({'username': user, 'key': tok}, f)
    k_id = f'{user}/ipscan-cl-shodan-{tag}'
    res = subprocess.run(['kaggle', 'kernels', 'status', k_id], capture_output=True, text=True)
    st = 'UNKNOWN'
    for l in res.stdout.splitlines():
        if 'has status' in l:
            st = l.split('has status')[-1].replace('"', '').replace('KernelWorkerStatus.', '').strip()
    shard_statuses[f'Shard {tag} ({user})'] = st

timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

summary = []
summary.append('================================================================================')
summary.append(f'STEP 7 - 10-MINUTE PROOF REPORT - {timestamp}')
summary.append('================================================================================')
summary.append(f'Pool Size:             {pool_size}')
summary.append(f'Dead Size:             {dead_size}')
summary.append(f'Suspect Size:          {suspect_size}')
summary.append(f'Part Files Remaining:  {part_files_count}')
summary.append('Shard Statuses:')
for name, st in shard_statuses.items():
    summary.append(f'  {name}: {st}')
summary.append('FLEET_CYCLE.txt Tail:')
for l in fleet_tail:
    summary.append(f'  {l}')
summary.append('================================================================================\n')

summary_text = '\n'.join(summary)
print(summary_text)

with open(morning_file, 'a', encoding='utf-8') as f:
    f.write(summary_text)

print('APPENDED TO work/MORNING.txt')
