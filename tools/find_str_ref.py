import subprocess

data = subprocess.run(["objdump", "-d", "/tmp/traff_cli"], capture_output=True, text=True, errors="ignore").stdout
for line in data.splitlines():
    if "# 0x1bcc90" in line or "# 1bcc90" in line:
        print(line)
