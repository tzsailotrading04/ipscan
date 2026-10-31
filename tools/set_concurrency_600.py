import pathlib, py_compile

target_dirs = sorted(list(pathlib.Path("kaggle").glob("cl_shodan*")))
print(f"Targeting {len(target_dirs)} directories.")

patched = 0
for d in target_dirs:
    f = d / "run.py"
    if not f.exists():
        continue
    content = f.read_text(encoding="utf-8")
    
    c_norm = content.replace("\r\n", "\n")
    if "DEFAULT_WORKERS = 1" in c_norm and "PROBE_CONCURRENCY = 20" in c_norm:
        c_norm = c_norm.replace("DEFAULT_WORKERS = 1", "DEFAULT_WORKERS = 2", 1)
        c_norm = c_norm.replace("PROBE_CONCURRENCY = 20", "PROBE_CONCURRENCY = 600", 1)
        if "\r\n" in content:
            c_norm = c_norm.replace("\n", "\r\n")
        f.write_text(c_norm, encoding="utf-8")
        py_compile.compile(str(f), doraise=True)
        patched += 1
    else:
        print(f"MISS in {d.name}")

print(f"Successfully updated and compile-checked {patched} files.")
