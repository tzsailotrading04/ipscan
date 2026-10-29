with open("/tmp/traff_cli", "rb") as f:
    content = f.read()

import re
# Look for json strings like {"token": or {"type": or {"version":
for m in re.finditer(rb'\{"[a-zA-Z0-9_]+":', content):
    print("JSON template:", content[m.start():m.start()+80])

# Also look for struct field names
fields = ["token", "device_name", "device_id", "version", "name", "client_version", "ip", "session_id"]
for fld in fields:
    matches = [m.start() for m in re.finditer(f'"{fld}"'.encode(), content)]
    print(f'Field "{fld}": {len(matches)} matches')
