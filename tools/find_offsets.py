import subprocess

# Find offset of "blnc.traffmonetizer.com" in binary
with open("/tmp/traff_cli", "rb") as f:
    content = f.read()

idx = 0
while True:
    pos = content.find(b"blnc.traffmonetizer.com", idx)
    if pos == -1:
        break
    print(f"Found 'blnc.traffmonetizer.com' at offset: 0x{pos:x} ({pos})")
    idx = pos + 1

# Also look for 1.3.3 or version strings
idx = 0
for needle in [b"1.3.3", b"Hello", b"HelloResponse", b"AcceptReady", b"BallanceMessage"]:
    pos = content.find(needle)
    if pos != -1:
        print(f"Found '{needle.decode()}' at offset: 0x{pos:x}")
