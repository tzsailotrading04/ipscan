import urllib.request
import re

url = "https://app.traffmonetizer.com/main.318e37ef9c96592f.js"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read().decode('utf-8', errors='ignore')
        matches = set(re.findall(r'https?://[a-zA-Z0-9.-]*traffmonetizer\.com[^"\' ]*', content))
        for m in sorted(list(matches)):
            print(m)
except Exception as e:
    print("Error:", e)
