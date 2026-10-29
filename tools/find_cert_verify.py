with open("/tmp/traff_cli", "rb") as f:
    content = f.read()

import re
matches = [m.start() for m in re.finditer(b"UnknownCA", content)]
print(f"Found 'UnknownCA' at: {[hex(m) for m in matches]}")

matches = [m.start() for m in re.finditer(b"BadCertificate", content)]
print(f"Found 'BadCertificate' at: {[hex(m) for m in matches]}")
