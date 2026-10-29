import glob
from collections import Counter

statuses = Counter()
last_lines = Counter()
balances = []

for i in range(1, 201):
    lp = f"/var/run/traffmonetizer/node_{i:03d}/cli.log"
    try:
        with open(lp, errors="ignore") as f:
            lines = [l.strip() for l in f if l.strip()]
        if not lines:
            statuses["EMPTY"] += 1
            continue
        last = lines[-1]
        last_lines[last] += 1
        for l in lines:
            if "ballance" in l.lower() or "balance" in l.lower():
                balances.append(l)
        if "connected" in last.lower() and "disconnected" not in last.lower():
            statuses["CONNECTED"] += 1
        elif "disconnected" in last.lower():
            statuses["DISCONNECTED"] += 1
        elif "connecting" in last.lower():
            statuses["CONNECTING"] += 1
        else:
            statuses["OTHER"] += 1
    except Exception as e:
        statuses["ERROR"] += 1

print("Statuses summary:", dict(statuses))
print("\nMost common last lines:")
for l, c in last_lines.most_common(5):
    print(f"  ({c}) {l}")

print(f"\nTotal balance lines found: {len(balances)}")
if balances:
    print("Sample balance lines:")
    for b in balances[:5]:
        print(" ", b)
