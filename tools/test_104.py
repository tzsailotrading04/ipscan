import socket

def main():
    s = socket.socket()
    s.settimeout(5.0)
    s.connect(("104.168.19.113", 443))
    req = b"CONNECT 88.99.65.143:443 HTTP/1.1\r\nHost: 88.99.65.143:443\r\n\r\n"
    s.sendall(req)
    resp = s.recv(1024)
    print("Response:", repr(resp))

if __name__ == "__main__":
    main()
