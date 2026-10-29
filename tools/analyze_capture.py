import subprocess

# Read packets from capture
with open("/mnt/d/DEpinFarm/tools/capture_blnc.py", "r") as f:
    text = f.read()

# Let's see the application data records after handshake
with open("/tmp/dump_full.txt", "w") as out:
    p = subprocess.Popen(["python3", "/mnt/d/DEpinFarm/tools/capture_blnc.py"], stdout=out)
    p.wait()

with open("/tmp/dump_full.txt", "r") as f:
    data = f.read()

print("Total length:", len(data))
# print lines around Application Data
for line in data.splitlines():
    if "length 0" not in line and "Flags [S" not in line:
        if any(h in line for h in ["Out IP", "In  IP", "1703 03"]):
            print(line[:100])
