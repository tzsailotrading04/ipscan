import ssl
import socket

def test_tls():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10.0)
    print("Connecting to 88.99.65.143:443 ...")
    sock.connect(("88.99.65.143", 443))
    print("Connected! Wrapping TLS...")
    ctx = ssl.create_default_context()
    # traffmonetizer connects to blnc.traffmonetizer.com or IP
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ssock = ctx.wrap_socket(sock, server_hostname="blnc.traffmonetizer.com")
    print("TLS handshake complete! Cipher:", ssock.cipher())
    ssock.sendall(b"GET / HTTP/1.1\r\nHost: blnc.traffmonetizer.com\r\n\r\n")
    resp = ssock.recv(512)
    print("Got response:", repr(resp[:100]))
    ssock.close()

if __name__ == "__main__":
    test_tls()
