import os
import subprocess

def main():
    results = []
    for i in range(1, 51):
        tag = f"strict_{i:03d}"
        ns = f"ns_{tag}"
        
        ns_exists = os.path.exists(f"/var/run/netns/{ns}")
        
        rs_pid_file = f"/var/run/traffmonetizer_test/{tag}/redsocks.pid"
        rs_alive = False
        if os.path.exists(rs_pid_file):
            try:
                pid = int(open(rs_pid_file).read().strip())
                rs_alive = os.path.exists(f"/proc/{pid}")
            except:
                pass

        cli_pids = subprocess.run(f"pgrep -f 'device-name {tag}'", shell=True, stdout=subprocess.PIPE, text=True).stdout.split()
        cli_alive = len(cli_pids) > 0
        
        ss_out = subprocess.run(f"ip netns exec {ns} ss -tan 2>/dev/null", shell=True, stdout=subprocess.PIPE, text=True).stdout
        estab = [l for l in ss_out.splitlines() if "ESTAB" in l]
        
        ip_s = subprocess.run(f"ip netns exec {ns} ip -s link show dev vc_ts{i:03d} 2>/dev/null", shell=True, stdout=subprocess.PIPE, text=True).stdout
        bytes_cnt = 0
        lines = ip_s.splitlines()
        for j, l in enumerate(lines):
            if ("RX:" in l or "TX:" in l) and j+1 < len(lines):
                parts = lines[j+1].split()
                if parts and parts[0].isdigit():
                    bytes_cnt += int(parts[0])

        results.append({
            "tag": tag,
            "ns": ns_exists,
            "redsocks": rs_alive,
            "traff_cli": cli_alive,
            "estab_conns": len(estab),
            "total_bytes": bytes_cnt
        })

    alive_conns = [r for r in results if r["estab_conns"] > 0]
    alive_all = [r for r in results if r["redsocks"] and r["traff_cli"] and r["estab_conns"] > 0]
    
    print(f"Total strict nodes evaluated: {len(results)}")
    print(f"Namespaces exist: {sum(1 for r in results if r['ns'])}")
    print(f"Redsocks running: {sum(1 for r in results if r['redsocks'])}")
    print(f"traff_cli running: {sum(1 for r in results if r['traff_cli'])}")
    print(f"Nodes with ESTAB TCP sockets: {len(alive_conns)}")
    print(f"Nodes with traffic > 10KB: {sum(1 for r in results if r['total_bytes'] > 10000)}")
    print(f"Fully verified alive (RS + CLI + ESTAB socket): {len(alive_all)}")

    dead = [r['tag'] for r in results if r['estab_conns'] == 0]
    print(f"Nodes without ESTAB socket ({len(dead)}): {', '.join(dead)}")

if __name__ == "__main__":
    main()
