import os
import subprocess
import json

REPO_ROOT = r"D:\DEpinFarm"
KAGGLE_JSON = os.path.expanduser("~/.kaggle/kaggle.json")

FLEET = [
    ("remruata", os.path.join(REPO_ROOT, "kaggle", "acct5", "access_token"), ["00", "01", "20", "21"]),
    ("lalthazualasailo", os.path.join(REPO_ROOT, "kaggle", "acct1", "access_token"), ["02", "03", "04", "05", "22"]),
    ("zomuanpuia", os.path.join(REPO_ROOT, "kaggle", "acct2", "access_token"), ["06", "07", "08", "09", "23"]),
    ("laldinthari", os.path.join(REPO_ROOT, "kaggle", "acct3", "access_token"), ["10", "11", "12", "13", "24"]),
    ("lalsangkima", os.path.join(REPO_ROOT, "kaggle", "acct4", "access_token"), ["15", "16", "17", "25", "26"]),
    ("spectatorlone", os.path.join(REPO_ROOT, "kaggle", "acct6", "access_token"), ["14", "18", "19", "27", "28"]),
    ("stephen34", os.path.join(REPO_ROOT, "kaggle", "stephen34", "access_token"), ["29", "30", "31", "32", "33"]),
]

def main():
    report = []
    for acct, token_file, shards in FLEET:
        tok = open(token_file).read().strip()
        os.environ["KAGGLE_API_TOKEN"] = tok
        os.environ["KAGGLE_KEY"] = tok
        os.environ["KAGGLE_USERNAME"] = acct
        with open(KAGGLE_JSON, "w", encoding="utf-8") as f:
            json.dump({"username": acct, "key": tok}, f)

        res_list = subprocess.run(["kaggle", "kernels", "list", "--mine"], capture_output=True, text=True)
        list_lines = res_list.stdout.splitlines()

        for s in shards:
            slug = f"{acct}/ipscan-cl-shodan-{s}"
            res_st = subprocess.run(["kaggle", "kernels", "status", slug], capture_output=True, text=True)
            out = (res_st.stdout + res_st.stderr).strip().replace("\n", " ")
            status = "UNKNOWN"
            if "RUNNING" in out:
                status = "RUNNING"
            elif "QUEUED" in out:
                status = "QUEUED"
            elif "COMPLETE" in out:
                status = "COMPLETE"
            elif "404" in out or "not found" in out.lower() or "denied" in out.lower():
                status = "NOT_FOUND_OR_FAILED"
            else:
                status = out

            last_run = "N/A"
            for line in list_lines:
                if slug in line:
                    parts = line.split()
                    for idx, p in enumerate(parts):
                        if "-" in p and ":" in parts[min(idx+1, len(parts)-1)]:
                            last_run = f"{p} {parts[idx+1]}"
                            break

            report.append({
                "shard": s,
                "account": acct,
                "status": status,
                "last_run": last_run
            })
            print(f"shard_{s} | {acct:16} | status: {status:15} | last_run: {last_run}")

if __name__ == "__main__":
    main()
