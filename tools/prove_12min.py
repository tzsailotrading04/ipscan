import os
import glob
import subprocess
import json
import time

repo = r'D:\DEpinFarm'
queue_dir = os.path.join(repo, 'ip', 'harvest', 'queue')
pool_file = os.path.join(repo, 'ip', 'harvest', 'real_pool.txt')
dead_file = os.path.join(repo, 'cache', 'pool_dead.txt')
suspect_file = os.path.join(repo, 'cache', 'pool_suspect.txt')
feed_log_file = os.path.join(repo, 'ipscan-cl-feed.log')
morning_file = os.path.join(repo, 'work', 'MORNING.txt')

def count_lines(path):
    if not os.path.exists(path): return 0
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return sum(1 for line in f if line.strip())

# 1. Queue files and queue lines
q_files = glob.glob(os.path.join(queue_dir, 'q_*.txt'))
q_files_count = len(q_files)
q_lines_count = sum(count_lines(f) for f in q_files)

# 2. Feed log tail and ok/err
feed_log_tail = []
feed_ok_err = "UNKNOWN"
if os.path.exists(feed_log_file):
    try:
        with open(feed_log_file, 'r', encoding='utf-8', errors='ignore') as f:
            data = json.load(f)
        lines = [d.get('data', '').strip() for d in data if 'data' in d and d.get('data', '').strip()]
        feed_log_tail = lines[-5:]
        for l in reversed(lines):
            if '[feed]' in l and 'src_ok=' in l:
                feed_ok_err = l
                break
    except Exception as e:
        feed_log_tail = [f"Error reading log: {e}"]

# 3. Shards 00 and 20 stats: req_s, cands
def get_shard_stats(shard_tag):
    sf = os.path.join(repo, 'ip', 'harvest', f'shodan_stats_v98_{shard_tag}.txt')
    req_s = 0.0
    cands = 0
    if os.path.exists(sf):
        try:
            with open(sf, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.startswith('req_s='):
                        req_s = float(line.split('=')[1].strip())
                    elif line.startswith('cands='):
                        cands = int(line.split('=')[1].strip())
        except Exception:
            pass
    return req_s, cands

req_s_00, cands_00 = get_shard_stats('00')
req_s_20, cands_20 = get_shard_stats('20')

# 4. Pool, dead, suspect sizes
pool_size = count_lines(pool_file)
dead_size = count_lines(dead_file)
suspect_size = count_lines(suspect_file)

# 5. RUNNING per account
KAGGLE_JSON = os.path.expanduser('~/.kaggle/kaggle.json')
FLEET_MAPPING = [
    ("remruata", os.path.join(repo, "kaggle", "acct5", "access_token"), ["00", "01", "20", "21"]),
    ("lalthazualasailo", os.path.join(repo, "kaggle", "acct1", "access_token"), ["02", "03", "04", "05", "22"]),
    ("zomuanpuia", os.path.join(repo, "kaggle", "acct2", "access_token"), ["06", "07", "08", "09", "23"]),
    ("laldinthari", os.path.join(repo, "kaggle", "acct3", "access_token"), ["10", "11", "12", "13", "24"]),
    ("lalsangkima", os.path.join(repo, "kaggle", "acct4", "access_token"), ["15", "16", "17", "25", "26"]),
    ("spectatorlone", os.path.join(repo, "kaggle", "acct6", "access_token"), ["14", "18", "19", "27", "28"]),
    ("stephen34", os.path.join(repo, "kaggle", "stephen34", "access_token"), ["29", "30", "31", "32", "33"]),
]

running_by_acct = {}
for user, tok_file, shard_list in FLEET_MAPPING:
    with open(tok_file) as f: tok = f.read().strip()
    os.environ['KAGGLE_API_TOKEN'] = tok
    os.environ['KAGGLE_USERNAME'] = user
    os.environ['KAGGLE_KEY'] = tok
    with open(KAGGLE_JSON, 'w') as f: json.dump({'username': user, 'key': tok}, f)
    cnt = 0
    for tag in shard_list:
        k_id = f'{user}/ipscan-cl-shodan-{tag}'
        res = subprocess.run(['kaggle', 'kernels', 'status', k_id], capture_output=True, text=True)
        if 'RUNNING' in res.stdout:
            cnt += 1
    # Check feeder on remruata
    if user == 'remruata':
        f_res = subprocess.run(['kaggle', 'kernels', 'status', 'remruata/ipscan-cl-feed'], capture_output=True, text=True)
        if 'RUNNING' in f_res.stdout:
            cnt += 1
    running_by_acct[user] = cnt

# 6. New proxies found in the last 12 minutes
now_ts = time.time()
twelve_min_ago = now_ts - 720
recent_proxies = []
for pf in glob.glob(os.path.join(repo, 'ip', 'harvest', 'verified_alive_part_*.txt')):
    try:
        if os.path.getmtime(pf) >= twelve_min_ago:
            with open(pf, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    ls = line.strip()
                    if ls:
                        recent_proxies.append(ls)
    except Exception:
        pass

timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

report = []
report.append('=' * 80)
report.append(f'BRIEF v98.182 PROOF AT 12 MINUTES - {timestamp}')
report.append('=' * 80)
report.append(f'Queue Files:           {q_files_count}')
report.append(f'Queue Lines:           {q_lines_count}')
report.append(f'Feed Log Tail:')
for l in feed_log_tail:
    report.append(f'  {l}')
report.append(f'Feed Summary (ok/err): {feed_ok_err}')
report.append('-' * 80)
report.append(f'Shard 00: req_s={req_s_00:.1f} | cands={cands_00}')
report.append(f'Shard 20: req_s={req_s_20:.1f} | cands={cands_20}')
report.append('-' * 80)
report.append(f'Verified Pool Size:    {pool_size}')
report.append(f'Dead Size:             {dead_size}')
report.append(f'Suspect Size:          {suspect_size}')
report.append('-' * 80)
report.append('RUNNING Sessions Per Account:')
for u, count in running_by_acct.items():
    max_cap = 5
    flag = 'OK' if count <= max_cap else 'EXCEEDED'
    report.append(f'  {u:<18}: {count}/{max_cap} [{flag}]')
report.append('-' * 80)
report.append(f'New Proxies Found in Last 12 Minutes: {len(recent_proxies)}')
if recent_proxies:
    report.append('Sample Recent Proxies:')
    for p in recent_proxies[:10]:
        report.append(f'  {p}')
report.append('=' * 80 + '\n')

report_text = '\n'.join(report)
print(report_text)

with open(morning_file, 'a', encoding='utf-8') as f:
    f.write(report_text)

print('APPENDED TO work/MORNING.txt')
