with open("/tmp/traff_cli", "rb") as f:
    content = f.read()

needle = b"String payload too large"
pos = content.find(needle)
print(f"Offset of '{needle.decode()}': 0x{pos:x} ({pos})")
