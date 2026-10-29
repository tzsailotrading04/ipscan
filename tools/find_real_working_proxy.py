import urllib.request
import ssl
from concurrent.futures import ThreadPoolExecutor
import sys

def test_full_proxy(proxy):
    endpoint = proxy.strip().split("\t")[0]
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    proxy_handler = urllib.request.ProxyHandler({'http': f'http://{endpoint}', 'https': f'http://{endpoint}'})
    opener = urllib.request.build_opener(proxy_handler, urllib.request.HTTPSHandler(context=ctx))
    try:
        req = urllib.request.Request("https://api.ipify.org", headers={'User-Agent': 'curl/8.14.1'})
        with opener.open(req, timeout=4.0) as resp:
            body = resp.read().decode().strip()
            proxy_ip = endpoint.split(":")[0]
            if body == proxy_ip or len(body.split(".")) == 4:
                return endpoint, True, body
            return endpoint, False, f"Mismatch body: {body[:30]}"
    except Exception as e:
        return endpoint, False, type(e).__name__

def main():
    with open(r"D:\DEpinFarm\ip\harvest\real_pool.txt", "r", encoding="utf-8") as f:
        dc_proxies = [l.strip() for l in f if "DATACENTER" in l][:300]

    print(f"Scanning {len(dc_proxies)} datacenter proxies for true https://api.ipify.org pass-through...")
    with ThreadPoolExecutor(max_workers=50) as ex:
        for res in ex.map(test_full_proxy, dc_proxies):
            endpoint, ok, info = res
            if ok:
                print(f"FOUND WORKING PROXY: {endpoint} -> Returned IP: {info}")
                with open(r"D:\DEpinFarm\work\working_datacenter_proxy.txt", "w") as out:
                    out.write(f"{endpoint}\n")
                sys.exit(0)

if __name__ == "__main__":
    main()
