with open("/tmp/traff_cli", "rb") as f:
    content = f.read()

needle = b"[base.tcp] send start type="
pos = content.find(needle)
print(f"Offset of '{needle.decode()}': 0x{pos:x} ({pos})")
