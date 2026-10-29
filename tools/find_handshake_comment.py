import subprocess

data = subprocess.run(["objdump", "-d", "/tmp/traff_cli"], capture_output=True, text=True, errors="ignore").stdout
for line in data.splitlines():
    if "# 0x1bc7c0" in line or "# 0x1bc7dd" in line:
        print(line)
