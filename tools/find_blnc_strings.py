import subprocess
import re

data = subprocess.run(["strings", "-a", "/tmp/traff_cli"], capture_output=True, text=True, errors="ignore").stdout
for line in data.splitlines():
    l = line.strip()
    if "blnc" in l.lower() or "srv-" in l.lower() or "traffmonetizer.com" in l.lower():
        print(l)
