import subprocess

data = subprocess.run(["objdump", "-d", "/tmp/traff_cli"], capture_output=True, text=True, errors="ignore").stdout
for line in data.splitlines():
    if "1bc7c0" in line:
        print(line)
