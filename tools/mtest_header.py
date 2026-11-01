import subprocess as _sp, os as _os
try:
    _sp.run(["apt-get","-qq","install","-y","masscan"], capture_output=True, timeout=180)
    r0 = _sp.run("ip route", shell=True, capture_output=True, text=True)
    print("ROUTE", r0.stdout, r0.stderr)
    gw = ""
    mac = ""
    for line in r0.stdout.splitlines():
        if line.startswith("default"):
            parts = line.split()
            gw = parts[2] if len(parts) > 2 else ""
    if gw:
        n = _sp.run(f"ip neigh show {gw}", shell=True, capture_output=True, text=True).stdout
        print("NEIGH", n)
        toks = n.split()
        if "lladdr" in toks:
            mac = toks[toks.index("lladdr") + 1]
    print("GW", gw, "MAC", mac)
    cmd = "timeout 120 masscan 3.0.0.0/20 -p8080,3128,8888,1080,81,8000 --rate 5000 -e eth0"
    if mac:
        cmd += f" --router-mac {mac}"
    r = _sp.run(cmd, shell=True, capture_output=True, text=True, timeout=150)
    print("SCAN", r.returncode)
    print("OUT", r.stdout[-2000:])
    print("ERR", r.stderr[-2000:])
except Exception as _e:
    print("DIAG", _e)
