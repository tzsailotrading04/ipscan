import struct

with open("/tmp/traff_cli", "rb") as f:
    code = f.read()

target = struct.pack("<Q", 0x1bcd2e)
pos = 0
while True:
    p = code.find(target, pos)
    if p == -1:
        break
    print(f"Found 64-bit pointer to 0x1bcd2e at: 0x{p:x}")
    pos = p + 1
