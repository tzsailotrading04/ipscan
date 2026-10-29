import struct

with open("/tmp/traff_cli", "rb") as f:
    code = f.read()

target = 0x1bcd2e

for i in range(0x1f000, 0x1ab000):
    for insn_len in [7, 6, 8]:
        next_ip = i + insn_len
        disp_target = target - next_ip
        # check if disp_target is at code[i+insn_len-4 : i+insn_len]
        packed = struct.pack("<i", disp_target)
        if code[i+insn_len-4 : i+insn_len] == packed:
            print(f"Found match at offset 0x{i:x} (len {insn_len}): {code[i:i+insn_len].hex()}")
