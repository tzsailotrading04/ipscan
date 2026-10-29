import subprocess
from concurrent.futures import ThreadPoolExecutor

TOKEN = open("/mnt/d/DEpinFarm/config/traffmonetizer.token").read().strip()

def start_cli(i):
    ns_name = f"ns_traff_{i:03d}"
    node_dir = f"/var/run/traffmonetizer/node_{i:03d}"
    dev_name = f"dc_node_{i:03d}"
    cmd = (
        f"export HOME={node_dir}; "
        f"nohup ip netns exec {ns_name} /tmp/traff_cli start accept "
        f"--token {TOKEN} --device-name {dev_name} > {node_dir}/cli.log 2>&1 &"
    )
    subprocess.run(cmd, shell=True)

with ThreadPoolExecutor(max_workers=20) as pool:
    list(pool.map(start_cli, range(1, 201)))

print("Restarted traff_cli across all 200 nodes.")
