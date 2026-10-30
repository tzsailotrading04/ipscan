import os
import json
from kaggle.api.kaggle_api_extended import KaggleApi

repo = r"D:\DEpinFarm"
tok = open(os.path.join(repo, "kaggle", "acct5", "access_token")).read().strip()
kj = os.path.expanduser("~/.kaggle/kaggle.json")
with open(kj, "w") as f:
    json.dump({"username": "remruata", "key": tok}, f)

api = KaggleApi()
api.authenticate()

kernels = api.kernels_list(mine=True, page_size=50)
print(f"Total kernels on remruata: {len(kernels)}")
for k in kernels:
    print(f"  title='{k.title}' ref='{k.ref}' last_run_time='{k.last_run_time}'")
    if k.ref:
        try:
            st = api.kernels_status(k.ref)
            print(f"    STATUS: {st.get('status')}")
        except Exception as e:
            print(f"    STATUS ERR: {e}")
