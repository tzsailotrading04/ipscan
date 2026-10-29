import subprocess

data = subprocess.run(["objdump", "-d", "/tmp/traff_cli"], capture_output=True, text=True, errors="ignore").stdout
for line in data.splitlines():
    if any(h in line for h in ["1f306a", "1f3010", "1f3126"]):
        print(line)
