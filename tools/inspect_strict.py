import glob, os

files = glob.glob(r"D:\DEpinFarm\**\*strict*", recursive=True) + glob.glob(r"D:\DEpinFarm\**\*pool*", recursive=True)
for f in sorted(set(files)):
    if f.endswith(".txt") or f.endswith(".json"):
        size = os.path.getsize(f)
        lines = len(open(f, errors="ignore").readlines()) if f.endswith(".txt") else "json"
        print(f"{os.path.relpath(f, r'D:\DEpinFarm')}: lines={lines}, size={size}")
