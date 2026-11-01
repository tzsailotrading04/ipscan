import pathlib
p = pathlib.Path("tools/verify_candidates.py")
t = p.read_text(encoding="utf-8")
old = 'if b" 200" not in resp.split(b"\\r\\n")[0]:'
new = 'first = resp.split(b"\\r\\n")[0]\n        if not (b" 200" in first or b" 407" in first):'
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("patched" if new in t else "FAILED")
