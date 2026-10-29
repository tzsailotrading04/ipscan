import glob

found = 0
for log in sorted(glob.glob("/var/run/traffmonetizer/node_*/cli.log")):
    with open(log, errors="ignore") as f:
        lines = f.readlines()
    conn_lines = [l.strip() for l in lines if "connected" in l.lower() and "disconnected" not in l.lower()]
    if conn_lines:
        found += 1
        print(f"=== {log} ({len(lines)} lines) ===")
        print("Last line:", lines[-1].strip() if lines else "")
        print("Matching line:", conn_lines[-1])
        if found >= 5:
            break
