import subprocess
import time

# Start tcpdump on port 443 for blnc.traffmonetizer.com
p_tcp = subprocess.Popen([
    "tcpdump", "-i", "any", "-n", "-s", "0", "-X",
    "host 88.99.65.143 or host 168.119.91.41"
], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

time.sleep(1)

# Start traff_cli for 4 seconds
p_cli = subprocess.Popen([
    "/tmp/traff_cli", "start", "accept",
    "--token", "EPLSQERjvyYUO2S91i1VlWYI1VA5qCckw2TC6384tuY=",
    "--device-name", "probe_test"
], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

time.sleep(4)
p_cli.terminate()
time.sleep(1)
p_tcp.terminate()

out, _ = p_tcp.communicate()
print(out.decode("latin1", errors="ignore")[:4000])
