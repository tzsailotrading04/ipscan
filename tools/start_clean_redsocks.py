import subprocess
from concurrent.futures import ThreadPoolExecutor

def start_redsocks(i):
    ns_name = f"ns_traff_{i:03d}"
    node_dir = f"/var/run/traffmonetizer/node_{i:03d}"
    cmd = f"ip netns exec {ns_name} /usr/bin/redsocks -c {node_dir}/redsocks.conf -p {node_dir}/redsocks.pid"
    subprocess.run(cmd, shell=True)

with ThreadPoolExecutor(max_workers=30) as pool:
    list(pool.map(start_redsocks, range(1, 201)))

print("Started clean redsocks across 200 nodes.")
