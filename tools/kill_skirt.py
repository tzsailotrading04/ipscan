import os
import subprocess
import time

def get_mem():
    out = subprocess.run("free -m", shell=True, stdout=subprocess.PIPE, text=True).stdout
    lines = out.strip().splitlines()
    # Mem: total used free shared buff/cache available
    parts = lines[1].split()
    return {
        "total": int(parts[1]),
        "used": int(parts[2]),
        "free": int(parts[3]),
        "available": int(parts[6])
    }

def main():
    m_before = get_mem()
    print("=== MEMORY BEFORE ===")
    print(f"Total: {m_before['total']} MB | Used: {m_before['used']} MB | Free: {m_before['free']} MB | Available: {m_before['available']} MB")

    # Find skirt processes
    ps_out = subprocess.run("ps -eo pid,args", shell=True, stdout=subprocess.PIPE, text=True).stdout
    skirt_pids = []
    for line in ps_out.splitlines():
        if "skirt_" in line and "python" not in line and "grep" not in line:
            parts = line.strip().split()
            if parts and parts[0].isdigit():
                skirt_pids.append(int(parts[0]))

    print(f"Found {len(skirt_pids)} skirt processes to kill.")
    for pid in skirt_pids:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass

    # Unmount any skirt namespaces if present
    ns_out = subprocess.run("ip netns list", shell=True, stdout=subprocess.PIPE, text=True).stdout
    skirt_ns = [l.split()[0] for l in ns_out.splitlines() if "skirt" in l]
    print(f"Found {len(skirt_ns)} skirt namespaces to delete.")
    for ns in skirt_ns:
        subprocess.run(f"ip netns del {ns}", shell=True)

    # Clean run dirs
    subprocess.run("rm -rf /var/run/traffmonetizer_test/skirt_* 2>/dev/null", shell=True)
    time.sleep(1)

    m_after = get_mem()
    print("\n=== MEMORY AFTER ===")
    print(f"Total: {m_after['total']} MB | Used: {m_after['used']} MB | Free: {m_after['free']} MB | Available: {m_after['available']} MB")

    freed_used = m_before["used"] - m_after["used"]
    gained_free = m_after["free"] - m_before["free"]
    gained_avail = m_after["available"] - m_before["available"]
    print(f"\nFreed Memory: {freed_used} MB (Free RAM increased by {gained_free} MB, Available increased by {gained_avail} MB)")

    # Verify remaining
    ps_verify = subprocess.run("ps -eo pid,args", shell=True, stdout=subprocess.PIPE, text=True).stdout
    remaining = [l for l in ps_verify.splitlines() if "skirt_" in l and "python" not in l]
    print(f"Remaining skirt processes: {len(remaining)}")

if __name__ == "__main__":
    main()
