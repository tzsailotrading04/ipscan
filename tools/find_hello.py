import subprocess

offset = 0x1bc00f # "Hello"
# Search in disassembly for 1bc00f
data = subprocess.run(["objdump", "-d", "/tmp/traff_cli"], capture_output=True, text=True, errors="ignore").stdout

for line in data.splitlines():
    if "1bc00f" in line:
        print(line)
