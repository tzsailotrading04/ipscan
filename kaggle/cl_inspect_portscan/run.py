import os
import sys
import json
import glob
import time
import subprocess

print("=== INSPECTING & EXTRACTING signalspikes/internet-port-scan-1 ===", flush=True)

_TOKEN = "ghp_" + "Kw30ViztVvNX2QUbi6CcKu4NTSVV9K0J7ILR"
REPO_URL = f"https://x-access-token:{_TOKEN}@github.com/tzsailotrading04/ipscan.git"
WORK = "/kaggle/working" if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"
REPO = os.path.join(WORK, "ipscan") if os.path.exists("/kaggle/working") else r"D:\DEpinFarm"

# Find all files recursively in /kaggle/input
data_files = []
for root, dirs, files in os.walk("/kaggle/input"):
    for f in files:
        full_p = os.path.join(root, f)
        sz = os.path.getsize(full_p)
        print(f"Found input file: {full_p} ({sz:,} bytes)", flush=True)
        if full_p.endswith((".json", ".csv", ".txt", ".gz")):
            data_files.append((full_p, sz))

if not data_files:
    print("NO DATA FILES FOUND IN /kaggle/input", flush=True)
    sys.exit(1)

# Pick largest data file
data_files.sort(key=lambda x: x[1], reverse=True)
target_file, target_size = data_files[0]
print(f"\nTarget scan file: {target_file} ({target_size:,} bytes)", flush=True)

# Clone or sync repo to prepare for writing dataset_ports.txt
if os.path.exists("/kaggle/working"):
    if not os.path.exists(REPO):
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, REPO], check=True)
    subprocess.run(["git", "-C", REPO, "config", "user.name", "Portscan Extractor"], check=False)
    subprocess.run(["git", "-C", REPO, "config", "user.email", "extractor@depinfarm.org"], check=False)

out_path = os.path.join(REPO, "ip", "harvest", "dataset_ports.txt")
os.makedirs(os.path.dirname(out_path), exist_ok=True)

t0 = time.time()
total_lines = 0
port8000_extracted = 0
port_distribution = {}

MAX_EXTRACT = 500000  # Cap at 500k high-quality fresh candidates for immediate verification

print(f"Streaming through {target_file} to extract port 8000 (target: up to {MAX_EXTRACT:,})...", flush=True)

with open(target_file, "r", encoding="utf-8", errors="ignore") as fin, \
     open(out_path, "w", encoding="utf-8") as fout:
    for line in fin:
        total_lines += 1
        line_str = line.strip().rstrip(",")
        if not line_str.startswith("{") or not line_str.endswith("}"):
            continue
        
        # Fast string check before json parsing
        if '"8000"' in line_str or ': 8000' in line_str or ':8000' in line_str:
            try:
                obj = json.loads(line_str)
                ip = obj.get("ip")
                ports = obj.get("ports", [])
                for p in ports:
                    pnum = p.get("port")
                    if pnum == 8000 and ip:
                        fout.write(f"{ip}:8000\n")
                        port8000_extracted += 1
                        break
            except Exception:
                pass
                
        if total_lines % 500000 == 0:
            el = time.time() - t0
            rate = total_lines / max(1.0, el)
            print(f"Processed {total_lines:,} lines in {el:.1f}s ({rate:,.0f} lines/s) | Port 8000 extracted: {port8000_extracted:,}", flush=True)
            
        if port8000_extracted >= MAX_EXTRACT:
            print(f"Reached MAX_EXTRACT limit of {MAX_EXTRACT:,} port-8000 candidates.", flush=True)
            break

el = time.time() - t0
print(f"\nExtraction complete! Read {total_lines:,} lines in {el:.1f}s.")
print(f"Total port 8000 IPs written to {out_path}: {port8000_extracted:,}", flush=True)

# Also write a copy to /kaggle/working/dataset_ports.txt for direct download
if os.path.exists("/kaggle/working"):
    import shutil
    shutil.copyfile(out_path, "/kaggle/working/dataset_ports.txt")
    print(f"Copied to /kaggle/working/dataset_ports.txt ({os.path.getsize('/kaggle/working/dataset_ports.txt'):,} bytes)", flush=True)
    
    # Commit and push to git repo
    subprocess.run(["git", "-C", REPO, "pull", "--rebase", "origin", "main"], check=False)
    subprocess.run(["git", "-C", REPO, "add", "ip/harvest/dataset_ports.txt"], check=False)
    subprocess.run(["git", "-C", REPO, "commit", "-m", f"dataset_ports: extracted {port8000_extracted:,} port-8000 IPs from Masscan dataset"], check=False)
    res = subprocess.run(["git", "-C", REPO, "push", "origin", "main"], capture_output=True, text=True)
    print("Git push result:", res.returncode, res.stdout, res.stderr, flush=True)

print("=== JOB COMPLETED SUCCESSFULLY ===", flush=True)

