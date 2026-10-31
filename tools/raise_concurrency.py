import pathlib, py_compile

target_dirs = sorted(list(pathlib.Path("kaggle").glob("cl_shodan*")))
print(f"Found {len(target_dirs)} shard directories.")

old_workers = """DEFAULT_WORKERS = 2
BACKOFF_WORKERS = 1"""

new_workers = """DEFAULT_WORKERS = 1
BACKOFF_WORKERS = 20
PROBE_CONCURRENCY = 20"""

old_sem = "sem = asyncio.Semaphore(6000)"
new_sem = "sem = asyncio.Semaphore(PROBE_CONCURRENCY)  # Strictly bounds concurrency to 20 parallel probes"

patched = 0
for d in target_dirs:
    f = d / "run.py"
    if not f.exists():
        continue
    content = f.read_text(encoding="utf-8")
    
    # Normalize for replacement
    content_norm = content.replace("\r\n", "\n")
    if old_workers in content_norm and old_sem in content_norm:
        content_norm = content_norm.replace(old_workers, new_workers, 1)
        content_norm = content_norm.replace(old_sem, new_sem, 1)
        # Restore CRLF if original had it
        if "\r\n" in content:
            content_norm = content_norm.replace("\n", "\r\n")
        f.write_text(content_norm, encoding="utf-8")
        py_compile.compile(str(f), doraise=True)
        patched += 1
    else:
        print(f"MISS in {d.name}")

print(f"Successfully patched and compile-checked {patched} files.")
