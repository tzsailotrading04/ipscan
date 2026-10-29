with open("/tmp/traff_cli", "rb") as f:
    f.seek(0x1bc000)
    chunk = f.read(0x1000)

printable = ""
for b in chunk:
    if 32 <= b <= 126:
        printable += chr(b)
    else:
        printable += "\n"

lines = [l.strip() for l in printable.splitlines() if len(l.strip()) >= 3]
for l in lines:
    print(l)
