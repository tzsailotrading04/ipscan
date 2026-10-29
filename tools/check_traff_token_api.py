import urllib.request
import json

with open("/mnt/d/DEpinFarm/config/traffmonetizer.token") as f:
    token = f.read().strip()

headers = {
    "Authorization": token,
    "Authorization": f"Bearer {token}",
    "User-Agent": "Mozilla/5.0"
}

endpoints = [
    "https://app.traffmonetizer.com/api/user/me",
    "https://app.traffmonetizer.com/api/devices",
    "https://app.traffmonetizer.com/api/stats",
    "https://data.traffmonetizer.com/api/user/me",
    "https://data.traffmonetizer.com/api/devices",
    "https://blnc.traffmonetizer.com/api/devices",
]

for ep in endpoints:
    for h in [{"Authorization": token}, {"Authorization": f"Bearer {token}"}]:
        try:
            req = urllib.request.Request(ep, headers=h)
            with urllib.request.urlopen(req, timeout=5) as resp:
                print(ep, "->", resp.status, resp.read().decode()[:200])
                break
        except urllib.error.HTTPError as e:
            pass
        except Exception as e:
            pass
