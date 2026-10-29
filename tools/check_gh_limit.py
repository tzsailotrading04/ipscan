import urllib.request, json
token = "ghp_" + "Kw30ViztVvNX2QUbi6CcKu4NTSVV9K0J7ILR"
req = urllib.request.Request("https://api.github.com/rate_limit", headers={"Authorization": f"token {token}", "User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        print("Search limit:", data["resources"]["search"])
        print("Core limit:", data["resources"]["core"])
except Exception as e:
    print("Error:", e)
