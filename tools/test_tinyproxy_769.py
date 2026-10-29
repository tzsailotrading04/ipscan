import socket

s = socket.socket()
s.settimeout(5.0)
s.connect(("104.168.19.113", 443))
req = b"CONNECT 67.213.124.163:769 HTTP/1.1\r\nHost: 67.213.124.163:769\r\n\r\n"
s.sendall(req)
resp = s.recv(1024)
print("Tinyproxy port 769 response:", repr(resp))
