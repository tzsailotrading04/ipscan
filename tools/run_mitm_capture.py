import socket
import ssl
import threading
import sys
import os
import subprocess
import time

def relay(src, dst, label):
    try:
        while True:
            data = src.recv(4096)
            if not data:
                break
            print(f"\n========================================================")
            print(f"[{label}] ({len(data)} bytes):")
            hex_str = " ".join(f"{b:02x}" for b in data)
            ascii_str = "".join(chr(b) if 32 <= b <= 126 else "." for b in data)
            print(f"HEX:   {hex_str}")
            print(f"ASCII: {ascii_str}")
            print(f"========================================================\n")
            sys.stdout.flush()
            dst.sendall(data)
    except Exception as e:
        pass
    finally:
        try: src.close()
        except: pass
        try: dst.close()
        except: pass

def handle_443(client_sock):
    try:
        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.load_cert_chain(certfile="/tmp/mitm/server.crt", keyfile="/tmp/mitm/server.key")
        tls_client = server_ctx.wrap_socket(client_sock, server_side=True)

        up_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        up_sock.connect(("88.99.65.143", 443))
        up_ctx = ssl.create_default_context()
        tls_upstream = up_ctx.wrap_socket(up_sock, server_hostname="blnc.traffmonetizer.com")

        t1 = threading.Thread(target=relay, args=(tls_client, tls_upstream, "CLIENT -> BLNC (443)"))
        t2 = threading.Thread(target=relay, args=(tls_upstream, tls_client, "BLNC (443) -> CLIENT"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except Exception as e:
        print("Error in 443 handler:", e)
        sys.stdout.flush()

def handle_769(client_sock):
    try:
        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.load_cert_chain(certfile="/tmp/mitm/server.crt", keyfile="/tmp/mitm/server.key")
        server_ctx.check_hostname = False
        tls_client = server_ctx.wrap_socket(client_sock, server_side=True)

        up_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        up_sock.connect(("67.213.124.163", 769))
        up_ctx = ssl.create_default_context()
        up_ctx.check_hostname = False
        up_ctx.verify_mode = ssl.CERT_NONE
        tls_upstream = up_ctx.wrap_socket(up_sock, server_hostname="srv-lax12.traffmonetizer.com")

        t1 = threading.Thread(target=relay, args=(tls_client, tls_upstream, "CLIENT -> RELAY (769)"))
        t2 = threading.Thread(target=relay, args=(tls_upstream, tls_client, "RELAY (769) -> CLIENT"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except Exception as e:
        print("Error in 769 handler:", e)
        sys.stdout.flush()

def start_server(port, handler):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(10)
    print(f"Listener ready on port {port}")
    sys.stdout.flush()
    while True:
        c, _ = srv.accept()
        threading.Thread(target=handler, args=(c,), daemon=True).start()

def main():
    t1 = threading.Thread(target=start_server, args=(8443, handle_443), daemon=True)
    t2 = threading.Thread(target=start_server, args=(8769, handle_769), daemon=True)
    t1.start()
    t2.start()
    print("MITM listeners started. Configuring ns_traff_001...")
    sys.stdout.flush()

    # Configure iptables in ns_traff_001 to redirect directly to MITM listeners on 10.99.0.1
    ipt = """
    ip netns exec ns_traff_001 iptables -t nat -F
    ip netns exec ns_traff_001 iptables -t nat -A OUTPUT -p tcp --dport 443 -j DNAT --to-destination 10.99.0.1:8443
    ip netns exec ns_traff_001 iptables -t nat -A OUTPUT -p tcp --dport 769 -j DNAT --to-destination 10.99.0.1:8769
    """
    subprocess.run(ipt, shell=True, check=True)

    # Launch traff_cli inside ns_traff_001 for 8 seconds
    print("Launching traff_cli inside ns_traff_001...")
    sys.stdout.flush()
    token = open("/mnt/d/DEpinFarm/config/traffmonetizer.token").read().strip()
    cmd = f"ip netns exec ns_traff_001 /tmp/traff_cli start accept --token {token} --device-name mitm_probe"
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    time.sleep(8)
    p.terminate()
    print("Finished capture.")

if __name__ == "__main__":
    main()
