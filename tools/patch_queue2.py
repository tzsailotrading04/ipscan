import pathlib

OLD = '''    for _pass in range(60):
        try:
            subprocess.run(["git", "fetch", "--depth", "1", "origin", "main"], cwd=REPO, capture_output=True, timeout=90)
            subprocess.run(["git", "checkout", "FETCH_HEAD", "--", "ip/harvest/queue"], cwd=REPO, capture_output=True, timeout=90)
        except Exception:
            pass
        _left = await consume_queue_stage()
        if not _left:
            break
        await asyncio.sleep(1)'''

NEW = '''    _empty = 0
    for _pass in range(600):
        try:
            subprocess.run(["git", "fetch", "--depth", "1", "origin", "main"], cwd=REPO, capture_output=True, timeout=90)
            subprocess.run(["git", "checkout", "FETCH_HEAD", "--", "ip/harvest/queue"], cwd=REPO, capture_output=True, timeout=90)
        except Exception:
            pass
        _left = await consume_queue_stage()
        if _left:
            _empty = 0
            await asyncio.sleep(1)
            continue
        _empty += 1
        if _empty >= 20:
            break
        await asyncio.sleep(30)'''

n = 0
for d in sorted(pathlib.Path("kaggle").glob("cl_shodan_*")):
    f = d / "run.py"
    s = f.read_text(encoding="utf-8")
    s_norm = s.replace("\r\n", "\n")
    if OLD in s_norm:
        s_patched = s_norm.replace(OLD, NEW, 1)
        # Preserve original line endings if CRLF was present
        if "\r\n" in s:
            s_patched = s_patched.replace("\n", "\r\n")
        f.write_text(s_patched, encoding="utf-8")
        n += 1
    else:
        print("MISS", d.name)
print("patched", n)
