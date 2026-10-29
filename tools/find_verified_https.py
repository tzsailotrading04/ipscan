import urllib.request
import ssl
from concurrent.futures import ThreadPoolExecutor

def test(p):
    endpoint = p.split("\t")[0]
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    handler = urllib.request.ProxyHandler({'https': f'http://{endpoint}'})
    opener = urllib.request.build_opener(handler, urllib.request.HTTPSHandler(context=ctx))
    try:
        req = urllib.request.Request("https://api.ipify.org", headers={'User-Agent': 'curl/8.14.1'})
        with opener.open(req, timeout=3.5) as r:
            ret_ip = r.read().decode().strip()
            return endpoint, ret_ip
    except Exception:
        return endpoint, None

with open(r"D:\DEpinFarm\ip\harvest\real_pool.txt", "r", encoding="utf-8") as f:
    lines = [l.strip() for l in f if "DATACENTER" in l]

print(f"Searching {len(lines)} proxies for true https://api.ipify.org...")
with ThreadPoolExecutor(max_workers=50) as ex:
    for ep, ret_ip in ex.map(test, lines):
        if ret_ip:
            print(f"VERIFIED_PROXY: {ep} -> {ret_ip}")
