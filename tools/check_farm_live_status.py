import os
import glob

base = "/var/run/traffmonetizer"
nodes = sorted(glob.glob(f"{base}/node_*"))
connected = []
connecting = []
disconnected = []
dead_or_no_log = []

for n in nodes:
    node_name = os.path.basename(n)
    log_p = os.path.join(n, "cli.log")
    if not os.path.exists(log_p):
        dead_or_no_log.append(node_name)
        continue
    try:
        with open(log_p, "r", errors="ignore") as f:
            lines = f.readlines()
        last_chunk = "".join(lines[-15:])
        if " - connected" in last_chunk or "ballance:" in last_chunk.lower():
            connected.append(node_name)
        elif " - connecting" in last_chunk:
            connecting.append(node_name)
        elif " - disconnected" in last_chunk:
            disconnected.append(node_name)
        else:
            dead_or_no_log.append(node_name)
    except Exception as e:
        dead_or_no_log.append(node_name)

print(f"Total nodes: {len(nodes)}")
print(f"CONNECTED: {len(connected)}")
print(f"CONNECTING: {len(connecting)}")
print(f"DISCONNECTED: {len(disconnected)}")
print(f"DEAD/OTHER: {len(dead_or_no_log)}")
