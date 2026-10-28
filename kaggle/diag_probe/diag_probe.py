import socket
import time
import subprocess
import os

print("=== STEP 1 - PROVE THE CONTAINER CAN CONNECT ===")
targets = [
    ("104.16.0.1", 8080),
    ("1.1.1.1", 443),
    ("8.8.8.8", 53),
    ("1.10.248.237", 80),
]

for host, port in targets:
    t0 = time.perf_counter()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3.0)
    try:
        s.connect((host, port))
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        print(f"connect {host}:{port} -> SUCCESS ({elapsed_ms:.1f}ms)")
        s.close()
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        print(f"connect {host}:{port} -> FAILURE ({elapsed_ms:.1f}ms) [{type(e).__name__}: {e}]")

print("\n=== STEP 4 - PORT EXHAUSTION & NETWORK CHECK ===")
# 1. ss -tan | awk '{print $1}' | sort | uniq -c | sort -rn | head
try:
    p1 = subprocess.Popen(["ss", "-tan"], stdout=subprocess.PIPE, text=True)
    p2 = subprocess.Popen(["awk", "{print $1}"], stdin=p1.stdout, stdout=subprocess.PIPE, text=True)
    p3 = subprocess.Popen(["sort"], stdin=p2.stdout, stdout=subprocess.PIPE, text=True)
    p4 = subprocess.Popen(["uniq", "-c"], stdin=p3.stdout, stdout=subprocess.PIPE, text=True)
    p5 = subprocess.Popen(["sort", "-rn"], stdin=p4.stdout, stdout=subprocess.PIPE, text=True)
    p6 = subprocess.Popen(["head", "-n", "10"], stdin=p5.stdout, stdout=subprocess.PIPE, text=True)
    p1.stdout.close()
    p2.stdout.close()
    p3.stdout.close()
    p4.stdout.close()
    p5.stdout.close()
    out, _ = p6.communicate()
    print("ss state distribution:")
    print(out.strip())
except Exception as e:
    print(f"ss command failed: {e}")

# 2. TIME-WAIT count specifically
try:
    res = subprocess.run("ss -tan | grep TIME-WAIT | wc -l", shell=True, capture_output=True, text=True)
    print("TIME-WAIT count:", res.stdout.strip())
except Exception as e:
    print(f"TIME-WAIT check failed: {e}")

# 3. Ephemeral port range
try:
    with open("/proc/sys/net/ipv4/ip_local_port_range", "r") as f:
        print("ip_local_port_range:", f.read().strip())
except Exception as e:
    print(f"port range read failed: {e}")

print("=== PROBE COMPLETE ===")
