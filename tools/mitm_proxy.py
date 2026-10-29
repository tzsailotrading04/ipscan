import socket
import ssl
import threading
import sys

def relay(src, dst, label):
    try:
        while True:
            data = src.recv(4096)
            if not data:
                break
            print(f"\n[{label}] ({len(data)} bytes):")
            # print hex and ascii
            hex_str = " ".join(f"{b:02x}" for b in data[:128])
            ascii_str = "".join(chr(b) if 32 <= b <= 126 else "." for b in data[:128])
            print(f"  HEX:   {hex_str}")
            print(f"  ASCII: {ascii_str}")
            if len(data) > 128:
                print(f"  ... +{len(data)-128} more bytes")
            sys.stdout.flush()
            dst.sendall(data)
    except Exception as e:
        pass
    finally:
        try: src.close()
        except: pass
        try: dst.close()
        except: pass

def handle_conn(client_sock, upstream_host, upstream_port):
    try:
        # Wrap client socket in server TLS
        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.load_cert_chain(certfile="/tmp/mitm/server.crt", keyfile="/tmp/mitm/server.key")
        tls_client = server_ctx.wrap_socket(client_sock, server_side=True)

        # Connect upstream with client TLS
        up_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        up_sock.connect((upstream_host, upstream_port))
        up_ctx = ssl.create_default_context()
        tls_upstream = up_ctx.wrap_socket(up_sock, server_hostname="blnc.traffmonetizer.com" if upstream_port == 443 else None)

        t1 = threading.Thread(target=relay, args=(tls_client, tls_upstream, f"CLIENT -> UPSTREAM:{upstream_port}"))
        t2 = threading.Thread(target=relay, args=(tls_upstream, tls_client, f"UPSTREAM:{upstream_port} -> CLIENT"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except Exception as e:
        print("MITM Error:", e)
        sys.stdout.flush()

def start_listener(port, upstream_host, upstream_port):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(10)
    print(f"Listening on 127.0.0.1:{port} -> {upstream_host}:{upstream_port}")
    sys.stdout.flush()
    while True:
        c, _ = srv.accept()
        threading.Thread(target=handle_conn, args=(c, upstream_host, upstream_port), daemon=True).start()

if __name__ == "__main__":
    t443 = threading.Thread(target=start_listener, args=(8443, "88.99.65.143", 443), daemon=True)
    t769 = threading.Thread(target=start_listener, args=(8769, "67.213.124.163", 769), daemon=True)
    t443.start()
    t769.start()
    t443.join()
    t769.join()
