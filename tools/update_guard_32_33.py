with open(r"D:\DEpinFarm\tools\fleet_guard.ps1", "r", encoding="utf-8") as f:
    text = f.read()

target = '    "acct6" = @("shodan_18","shodan_19")'
replacement = '    "acct6" = @("shodan_18","shodan_19")\n    # Shards 32 and 33 permanently removed from revive list to free 2 slots on stephen34\n    "stephen34" = @("shodan_29","shodan_30","shodan_31")'

if target in text:
    text = text.replace(target, replacement, 1)
    with open(r"D:\DEpinFarm\tools\fleet_guard.ps1", "w", encoding="utf-8") as f:
        f.write(text)
    print("SUCCESS: fleet_guard.ps1 updated")
else:
    print("FAILED: target not found")
