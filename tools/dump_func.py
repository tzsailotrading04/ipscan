import subprocess

data = subprocess.run(["objdump", "-d", "--start-address=0x4f700", "--stop-address=0x4fb00", "/tmp/traff_cli"], capture_output=True, text=True, errors="ignore").stdout
print(data)
