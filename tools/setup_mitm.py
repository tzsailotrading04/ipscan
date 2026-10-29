import os
import subprocess

def run(cmd):
    return subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)

# 1. Generate local CA and cert for blnc.traffmonetizer.com and srv-*.traffmonetizer.com
os.makedirs("/tmp/mitm", exist_ok=True)
run("openssl req -x509 -newkey rsa:2048 -nodes -keyout /tmp/mitm/ca.key -out /tmp/mitm/ca.crt -days 365 -subj '/CN=TraffMitmCA'")

# Generate leaf cert for *.traffmonetizer.com
ext = """
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = blnc.traffmonetizer.com
DNS.2 = *.traffmonetizer.com
"""
with open("/tmp/mitm/ext.cnf", "w") as f:
    f.write(ext)

run("openssl req -newkey rsa:2048 -nodes -keyout /tmp/mitm/server.key -out /tmp/mitm/server.csr -subj '/CN=blnc.traffmonetizer.com'")
run("openssl x509 -req -in /tmp/mitm/server.csr -CA /tmp/mitm/ca.crt -CAkey /tmp/mitm/ca.key -CAcreateserial -out /tmp/mitm/server.crt -days 365 -extfile /tmp/mitm/ext.cnf")

# 2. Append CA to system store (/etc/ssl/cert.pem)
with open("/tmp/mitm/ca.crt", "r") as f:
    ca_pem = f.read()

with open("/etc/ssl/cert.pem", "r") as f:
    orig_certs = f.read()

if "TraffMitmCA" not in orig_certs:
    with open("/etc/ssl/cert.pem", "a") as f:
        f.write("\n# TraffMitmCA\n" + ca_pem)
    print("Appended TraffMitmCA to /etc/ssl/cert.pem")
else:
    print("TraffMitmCA already in /etc/ssl/cert.pem")

print("MITM certificates ready.")
