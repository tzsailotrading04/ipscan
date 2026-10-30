import os
import requests

repo = r"D:\DEpinFarm"
tok = open(os.path.join(repo, "kaggle", "acct5", "access_token")).read().strip()
r = requests.get("https://www.kaggle.com/api/v1/kernels/list", auth=("remruata", tok), params={"mine": True, "pageSize": 50})
print("Status:", r.status_code)
if r.status_code == 200:
    kernels = r.json()
    print(f"Total returned: {len(kernels)}")
    for k in kernels:
        ref = k.get("ref")
        # Check session status
        st_r = requests.get(f"https://www.kaggle.com/api/v1/kernels/status", auth=("remruata", tok), params={"kernel": ref})
        print(f"  {ref}: {st_r.json() if st_r.status_code==200 else st_r.status_code}")
else:
    print("Response:", r.text[:500])
