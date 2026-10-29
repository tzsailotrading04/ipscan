with open("/tmp/traff_cli", "rb") as f:
    content = f.read()

import re
matches = set(re.findall(rb'/[a-zA-Z0-9_/-]{3,50}', content))
for m in sorted(matches):
    try:
        s = m.decode('ascii')
        if any(w in s for w in ["api", "app", "token", "auth", "dev", "node", "bal", "stat", "hand", "conf", "reg"]):
            print(s)
    except:
        pass
