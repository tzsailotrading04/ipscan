import os
import sys
import subprocess
import resource
import time
import ipaddress
import shutil
import random

SLICE_IDX = 14
KERNEL_SLUG = "laldinthari/ipscan-cl-o"
_TOKEN = "ghp_" + "Kw30ViztVvNX2QUbi6CcKu4NTSVV9K0J7ILR"
REPO_URL = f"https://x-access-token:{_TOKEN}@github.com/tzsailotrading04/ipscan.git"

START_TIME = time.time()
HARD_STOP_SECS = 10 * 3600  # 10 hours

SOCKS_PORTS = {"1080", "1081", "1082", "1083", "1088", "10801", "10808", "10809", "4145", "4153", "2080", "9050"}

def log(msg):
    print(msg, flush=True)

def main():
    log("=" * 60)
    log(f"STARTING V46 RUN: SLICE={SLICE_IDX} KERNEL={KERNEL_SLUG}")
    log("=" * 60)

    # 1. STEP: probe environment
    log("STEP: probe & tune environment")
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
        log(f"ulimit set to {hard}")
    except Exception as e:
        log(f"ulimit set error: {e}")

    for k, v in [
        ("net.ipv4.ip_local_port_range", "1024 65535"),
        ("net.ipv4.tcp_tw_reuse", "1"),
        ("net.ipv4.tcp_fin_timeout", "15")
    ]:
        subprocess.run(f"sysctl -w {k}='{v}'", shell=True, capture_output=True)

    working_dir = "/kaggle/working"
    repo_dir = os.path.join(working_dir, "ipscan")

    # 2. STEP: ensure Go & scanner
    log("STEP: ensure Go & scanner")
    harvest_bin = os.path.join(working_dir, "harvest")
    go_bin = shutil.which("go")
    if not go_bin and os.path.exists("/usr/local/go/bin/go"):
        go_bin = "/usr/local/go/bin/go"
        os.environ["PATH"] = "/usr/local/go/bin:" + os.environ.get("PATH", "")

    if not go_bin:
        log("Downloading Go 1.22.5...")
        dl_res = subprocess.run("curl -sSL --max-time 120 https://go.dev/dl/go1.22.5.linux-amd64.tar.gz | tar -C /usr/local -xz", shell=True)
        if dl_res.returncode == 0:
            os.environ["PATH"] = "/usr/local/go/bin:" + os.environ.get("PATH", "")
            go_bin = "/usr/local/go/bin/go"

    # Clone repo with token
    log("STEP: git clone / pull repo")
    if os.path.exists(repo_dir):
        subprocess.run(["git", "-C", repo_dir, "pull"], check=False)
    else:
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, repo_dir], check=True)

    # Configure git committer
    subprocess.run(["git", "-C", repo_dir, "config", "user.name", "Kaggle Worker"], check=False)
    subprocess.run(["git", "-C", repo_dir, "config", "user.email", "worker@depinfarm.org"], check=False)

    # Build or copy harvest
    repo_harvest = os.path.join(repo_dir, "ip", "harvest", "harvest")
    built_ok = False
    if go_bin and os.path.exists(os.path.join(repo_dir, "ip", "harvest", "main.go")):
        build_res = subprocess.run(f"cd {os.path.join(repo_dir, 'ip', 'harvest')} && go build -o {harvest_bin} main.go", shell=True, capture_output=True, text=True)
        if build_res.returncode == 0 and os.path.exists(harvest_bin):
            subprocess.run(["chmod", "+x", harvest_bin], check=True)
            log("BUILD_OK")
            built_ok = True
        else:
            log(f"BUILD_FAILED: {build_res.stderr}")

    if not built_ok:
        if os.path.exists(repo_harvest):
            shutil.copy2(repo_harvest, harvest_bin)
            subprocess.run(["chmod", "+x", harvest_bin], check=True)
            log("BUILD_OK (using repo precompiled binary)")
        else:
            log("FATAL: No harvest binary could be built or found!")
            sys.exit(1)

    # 3. STEP: load round, ports, ranges
    log("STEP: load round, ports, and ground ranges")
    round_file = os.path.join(repo_dir, "work", "round.txt")
    round_val = 0
    if os.path.exists(round_file):
        try:
            round_val = int(open(round_file, "r", encoding="utf-8").read().strip())
        except Exception:
            round_val = 0

    ports_file = os.path.join(repo_dir, "ip", "pe_ports.txt")
    ports = []
    with open(ports_file, "r", encoding="utf-8") as f:
        for line in f:
            p = line.strip()
            if p:
                ports.append(p)

    ranges_file = os.path.join(repo_dir, "data", "ranges_all.txt")
    cidrs = []
    with open(ranges_file, "r", encoding="utf-8") as f:
        for line in f:
            c = line.strip()
            if c:
                cidrs.append(c)

    # STEP 2 Arithmetic
    P = len(ports)
    N = len(cidrs)
    ROUNDS = 10
    total_units = P * N
    units_per_round = total_units // ROUNDS
    slice_size = units_per_round // 20
    my_start = round_val * units_per_round + SLICE_IDX * slice_size
    my_end = my_start + slice_size - 1

    log(f"SLICE {SLICE_IDX} ROUND {round_val} START {my_start} END {my_end}")

    # Control targets
    control_file = os.path.join(repo_dir, "ip", "control_fresh.txt")
    if not os.path.exists(control_file):
        control_file = os.path.join(repo_dir, "ip", "pub.txt")

    control_targets = []
    control_set = set()
    if os.path.exists(control_file):
        with open(control_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                s = line.strip()
                if s:
                    control_targets.append(s)
                    control_set.add(s)

    # Hits tracking
    hits_local = os.path.join(working_dir, f"hits_{SLICE_IDX}.txt")
    seen_addrs = set()
    if os.path.exists(hits_local):
        with open(hits_local, "r", encoding="utf-8", errors="ignore") as f:
            for l in f:
                p = l.strip().split()
                if p:
                    seen_addrs.add(p[0])

    total_scanned_targets = 0
    total_alive_hits = 0
    total_new_exits = 0
    seen_exit_ips = set()
    last_git_push = time.time()

    def push_hits_to_repo(force=False):
        nonlocal last_git_push
        now = time.time()
        if not force and (now - last_git_push < 1800):  # 30 min
            return
        if not os.path.exists(hits_local):
            return

        for attempt in range(5):
            try:
                subprocess.run(["git", "-C", repo_dir, "pull", "--rebase", "origin", "main"], capture_output=True, check=False)
                repo_hits_dir = os.path.join(repo_dir, "hits")
                os.makedirs(repo_hits_dir, exist_ok=True)
                dest = os.path.join(repo_hits_dir, f"hits_{SLICE_IDX}.txt")
                shutil.copy2(hits_local, dest)
                subprocess.run(["git", "-C", repo_dir, "add", f"hits/hits_{SLICE_IDX}.txt"], check=True)
                subprocess.run(["git", "-C", repo_dir, "commit", "-m", f"update hits_{SLICE_IDX} at {int(now)}"], capture_output=True, check=False)
                r = subprocess.run(["git", "-C", repo_dir, "push", "origin", "main"], capture_output=True, text=True)
                if r.returncode == 0:
                    log(f"GIT_PUSH_OK {SLICE_IDX}")
                    last_git_push = now
                    break
                else:
                    time.sleep(random.randint(2, 8))
            except Exception as e:
                log(f"git push attempt {attempt+1} error: {e}")
                time.sleep(3)

    # 4. WORK-LOOP: chunk into ~2,000,000 targets per chunk
    cur_idx = my_start
    is_first_chunk = True

    while cur_idx <= my_end:
        elapsed_total = time.time() - START_TIME
        if elapsed_total >= HARD_STOP_SECS:
            log(f"HARD_STOP reached at {elapsed_total:.0f}s. Final checkpoint...")
            break

        cur_port_idx = cur_idx // N
        if cur_port_idx >= P:
            break
        cur_port = ports[cur_port_idx]
        cur_proto = "socks5" if cur_port in SOCKS_PORTS else "http"
        cur_dial_ms = 750
        cur_read_ms = 30000 if cur_proto == "socks5" else 8000

        chunk_cidrs = []
        chunk_target_count = 0

        while cur_idx <= my_end:
            p_idx = cur_idx // N
            if p_idx >= P:
                break
            p = ports[p_idx]
            proto = "socks5" if p in SOCKS_PORTS else "http"
            if p != cur_port or proto != cur_proto:
                break

            c = cidrs[cur_idx % N]
            try:
                num = ipaddress.IPv4Network(c).num_addresses
                chunk_cidrs.append(c)
                chunk_target_count += num
                cur_idx += 1
                if chunk_target_count >= 2000000:
                    break
            except Exception:
                cur_idx += 1

        if not chunk_cidrs:
            continue

        target_file = os.path.join(working_dir, f"t_{SLICE_IDX}.txt")
        out_file = os.path.join(working_dir, f"out_{SLICE_IDX}.txt")
        if os.path.exists(out_file):
            os.remove(out_file)

        written_count = 0
        with open(target_file, "w", encoding="utf-8", newline="\n") as tf:
            if is_first_chunk and control_targets:
                for ct in control_targets:
                    tf.write(f"{ct}\n")
                    written_count += 1
            for c in chunk_cidrs:
                try:
                    net = ipaddress.IPv4Network(c)
                    s_int = int(net.network_address)
                    e_int = int(net.broadcast_address)
                    for u in range(s_int, e_int + 1):
                        tf.write(f"{ipaddress.IPv4Address(u)}:{cur_port}\n")
                        written_count += 1
                except Exception:
                    pass

        if is_first_chunk:
            try:
                warmup_target = os.path.join(working_dir, "warmup_targets.txt")
                with open(target_file, "r", encoding="utf-8", errors="ignore") as tf_in, \
                     open(warmup_target, "w", encoding="utf-8", newline="\n") as tf_out:
                    for idx, line in enumerate(tf_in):
                        if idx >= 50000:
                            break
                        tf_out.write(line)
                warmup_devnull = "/dev/null" if os.name != "nt" else os.path.join(working_dir, "warmup_null.txt")
                cmd_warmup = [
                    harvest_bin,
                    warmup_target,
                    warmup_devnull,
                    "24000",
                    str(cur_dial_ms),
                    str(cur_read_ms),
                    cur_proto
                ]
                env_warmup = os.environ.copy()
                env_warmup["CONCURRENCY"] = "24000"
                env_warmup["DIAL_TIMEOUT_MS"] = str(cur_dial_ms)
                env_warmup["READ_TIMEOUT_MS"] = str(cur_read_ms)
                env_warmup["PROTO"] = cur_proto
                subprocess.run(cmd_warmup, env=env_warmup, check=False)
                try:
                    if os.path.exists(warmup_target):
                        os.remove(warmup_target)
                except Exception:
                    pass
                log("WARMUP_DONE")
            except Exception as e:
                log(f"WARMUP_ERR: {e}")

        # Execute scanner
        cmd = [
            harvest_bin,
            target_file,
            out_file,
            "24000",
            str(cur_dial_ms),
            str(cur_read_ms),
            cur_proto
        ]
        env = os.environ.copy()
        env["CONCURRENCY"] = "24000"
        env["DIAL_TIMEOUT_MS"] = str(cur_dial_ms)
        env["READ_TIMEOUT_MS"] = str(cur_read_ms)
        env["PROTO"] = cur_proto

        t0 = time.time()
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, text=True)
        for line in proc.stdout:
            l = line.strip()
            if l.startswith("ARGS") or "error" in l.lower():
                log(f"  [{cur_proto}:{cur_port}] {l}")
        proc.wait()
        elapsed_chunk = time.time() - t0

        # Parse output
        chunk_alive = 0
        control_alive = 0

        if os.path.exists(out_file):
            with open(out_file, "r", encoding="utf-8", errors="ignore") as out_f, \
                 open(hits_local, "a", encoding="utf-8", newline="\n") as hits_f:
                for line in out_f:
                    l = line.strip()
                    if not l:
                        continue
                    parts = l.split()
                    if not parts:
                        continue
                    addr = parts[0]

                    if is_first_chunk and addr in control_set:
                        control_alive += 1
                        continue

                    chunk_alive += 1
                    total_alive_hits += 1

                    if len(parts) >= 2:
                        exit_ip = parts[1]
                        if exit_ip not in seen_exit_ips:
                            seen_exit_ips.add(exit_ip)
                            total_new_exits += 1

                    if addr not in seen_addrs:
                        seen_addrs.add(addr)
                        hits_f.write(f"{l}\n")

            try:
                os.remove(out_file)
            except Exception:
                pass

        try:
            os.remove(target_file)
        except Exception:
            pass

        if is_first_chunk and control_targets:
            control_pct = (control_alive / len(control_targets)) * 100
            log(f"CONTROL {control_alive}/{len(control_targets)} = {control_pct:.2f}%")
            is_first_chunk = False

        pure_targets = written_count - (len(control_targets) if is_first_chunk else 0)
        total_scanned_targets += pure_targets
        rate = int(pure_targets / elapsed_chunk) if elapsed_chunk > 0 else 0

        log(f"CHUNK src={SLICE_IDX} round={round_val} port={cur_port} targets={pure_targets} alive={chunk_alive} rate={rate}/s time={elapsed_chunk:.1f}s")
        push_hits_to_repo(force=False)

    # FINAL EXIT
    push_hits_to_repo(force=True)
    total_elapsed = time.time() - START_TIME
    final_rate = int(total_scanned_targets / total_elapsed) if total_elapsed > 0 else 0
    log(f"FINAL {SLICE_IDX} targets={total_scanned_targets} alive={total_alive_hits} new_exits={total_new_exits} rate={final_rate}/s")
    log("ALL_DONE")

if __name__ == "__main__":
    main()
