import subprocess

data = subprocess.run(["objdump", "-d", "--start-address=0x55200", "--stop-address=0x55600", "/tmp/traff_cli"], capture_output=True, text=True, errors="ignore").stdout
print(data)
