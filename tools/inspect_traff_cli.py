import subprocess

data = subprocess.run(["strings", "/tmp/traff_cli"], capture_output=True, text=True, errors="ignore").stdout
matches = set()
for line in data.splitlines():
    l = line.strip()
    if any(k in l.lower() for k in ["traffmonetizer", "srv-", "blnc", "authorization", "token", "device_id", "device_name", "connect", "/api"]):
        if 4 < len(l) < 100:
            matches.add(l)

for m in sorted(matches):
    print(m)
