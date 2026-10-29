import random
from collections import defaultdict

def main():
    pool_file = r"D:\DEpinFarm\ip\harvest\real_pool.txt"
    out_file = r"D:\DEpinFarm\work\traff_200_proxies.txt"
    
    ip_to_ports = defaultdict(list)
    total_dc = 0
    with open(pool_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 3 and parts[2] == "DATACENTER":
                total_dc += 1
                endpoint = parts[0]
                ip, port = endpoint.split(":")
                ip_to_ports[ip].append(port)
                
    unique_ips = list(ip_to_ports.keys())
    print(f"Total DATACENTER entries: {total_dc}")
    print(f"Unique DATACENTER IPs: {len(unique_ips)}")
    
    # Random sample of 200 distinct IPs
    random.seed(42)  # reproducible random
    chosen_ips = random.sample(unique_ips, min(200, len(unique_ips)))
    
    chosen_proxies = []
    for ip in chosen_ips:
        # Pick random port for this IP if multiple
        port = random.choice(ip_to_ports[ip])
        chosen_proxies.append(f"{ip}:{port}")
        
    with open(out_file, "w", encoding="utf-8") as f:
        for proxy in chosen_proxies:
            f.write(f"{proxy}\n")
            
    print(f"Selected exactly {len(chosen_proxies)} proxies (one per IP) saved to {out_file}")

if __name__ == "__main__":
    main()
