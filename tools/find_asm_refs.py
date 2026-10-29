import subprocess

# Look for references to offset 0x1bc96b in .text
offset = 0x1bc96b
data = subprocess.run(["objdump", "-d", "/tmp/traff_cli"], capture_output=True, text=True, errors="ignore").stdout

# Find lines referencing 1bc96b
print("Searching for instructions referencing string...")
found = 0
for line in data.splitlines():
    if "1bc96b" in line or "blnc" in line:
        print(line)
        found += 1
        if found >= 20:
            break
