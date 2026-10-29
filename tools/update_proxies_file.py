with open("/mnt/d/DEpinFarm/work/traff_200_proxies.txt") as f:
    lines = [l.strip() for l in f if l.strip()]

if lines[0] != "104.168.19.113:443":
    lines = [l for l in lines if not l.startswith("104.168.19.113")]
    lines = ["104.168.19.113:443"] + lines[:199]
    with open("/mnt/d/DEpinFarm/work/traff_200_proxies.txt", "w") as f:
        for l in lines:
            f.write(l + "\n")

print("Total proxies:", len(lines))
print("First proxy:", lines[0])
print("Second proxy:", lines[1])
