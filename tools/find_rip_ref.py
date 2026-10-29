import struct

with open("/tmp/traff_cli", "rb") as f:
    code = f.read()

target = 0x1bcd2e
# Look for 4-byte displacement in 7-byte instruction:
# e.g. 48 8d 05 [disp32]
# where next_ip = file_offset + 7 (assuming file offset == vaddr in static-pie)
for i in range(len(code) - 7):
    # Check 7-byte instructions with 32-bit RIP-relative displacement
    disp = struct.unpack("<i", code[i+3:i+7])[0]
    next_ip = i + 7
    if next_ip + disp == target:
        print(f"Found rip-relative ref at offset: 0x{i:x}")
