import urllib.request
import ssl
import sys

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

with open(r"D:\DEpinFarm\ip\harvest\real_pool.txt", "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if "DATACENTER" in line:
            parts = line.split("\t")
            endpoint = parts[0]
            ip, port = endpoint.split(":")
            # Try connecting through proxy
            proxy_handler = urllib.request.ProxyHandler({'http': f'http://{endpoint}', 'https': f'http://{endpoint}'})
            opener = urllib.request.build_opener(proxy_handler)
            try:
                req = urllib.request.Request("http://api.ipify.org", headers={'User-Agent': 'Mozilla/5.0'})
                with opener.open(req, timeout=3.0) as resp:
                    remote_ip = resp.read().decode('utf-8').strip()
                    print(f"FOUND_WORKING: {endpoint} -> Remote: {remote_ip}")
                    with open(r"D:\DEpinFarm\work\single_test_proxy.txt", "w") as out:
                        out.write(f"{endpoint}\n")
                    sys.exit(0)
            except Exception as e:
                continue
print("No proxy responded in first pass")
