import subprocess

data = subprocess.run(["strings", "-a", "-n", "5", "/tmp/traff_cli"], capture_output=True, text=True, errors="ignore").stdout
for l in data.splitlines():
    if any(k in l for k in ["[base.", "traffmonetizer", "1.3.3", "handshake", "balancer"]):
        print(l)
