import subprocess, time, ipaddress

subprocess.run("apt-get -qq update -y && apt-get -qq install -y golang-go", shell=True)
subprocess.run("git clone -q https://github.com/Thazuala04/ipscan.git /kaggle/working/ipscan", shell=True)
subprocess.run("sed -i 's/make(chan struct{}, 250)/make(chan struct{}, 4000)/' /kaggle/working/ipscan/ip/harvest/main.go", shell=True)
subprocess.run("cd /kaggle/working/ipscan/ip/harvest && (go mod init harvest || true) && go build -o /kaggle/working/harvest .", shell=True)

t = time.time()
subprocess.run(["/kaggle/working/harvest", "/kaggle/working/ipscan/ip/pub.txt", "/kaggle/working/ctrl.txt"])
tot = sum(1 for _ in open("/kaggle/working/ipscan/ip/pub.txt"))
alive = sum(1 for _ in open("/kaggle/working/ctrl.txt"))
print(f"CONTROL {alive}/{tot} = {alive/tot*100:.2f}%")

ports = [8080, 999, 1080, 8082, 3128, 1111, 5678, 8181, 8000, 8888]
with open("/kaggle/working/targets.txt", "w") as f:
    for ip in ipaddress.ip_network("1.0.0.0/16").hosts():
        s = str(ip)
        for p in ports:
            f.write(f"{s}:{p}\n")

t = time.time()
subprocess.run(["/kaggle/working/harvest", "/kaggle/working/targets.txt", "/kaggle/working/hits.txt"])
d = time.time() - t
tot = sum(1 for _ in open("/kaggle/working/targets.txt"))
alive = sum(1 for _ in open("/kaggle/working/hits.txt"))
print(f"SCAN {tot} in {d:.0f}s = {tot/d:.0f}/s alive {alive}")
