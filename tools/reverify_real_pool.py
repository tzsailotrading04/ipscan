import socket
import ssl
import time
import os
import shutil
from concurrent.futures import ThreadPoolExecutor

ssl_ctx = ssl.create_default_context()

def probe_strict(entry):
    parts = entry.strip().split("\t")
    endpoint = parts[0]
    target = parts[1] if len(parts) > 1 and "." in parts[1] else "speed.cloudflare.com"
    timeout = 3.5

    try:
        ip, port_s = endpoint.split(":", 1)
        port = int(port_s)
    except Exception:
        return entry, False, "BAD_FMT"

    # Try target first, then fallback to alternate target if CONNECT rejected
    targets_to_try = [target]
    if target != "www.google.com":
        targets_to_try.append("www.google.com")

    last_fail = "UNKNOWN"
    for t in targets_to_try:
        s = None
        ss = None
        try:
            s = socket.create_connection((ip, port), timeout=timeout)
            req = f"CONNECT {t}:443 HTTP/1.1\r\nHost: {t}:443\r\n\r\n".encode()
            s.sendall(req)
            s.settimeout(timeout)
            resp = b""
            while b"\r\n\r\n" not in resp:
                chunk = s.recv(512)
                if not chunk: break
                resp += chunk
                if len(resp) > 2048: break

            first_line = resp.split(b"\r\n")[0]
            if not (b" 200" in first_line or b"HTTP/1.1 200" in first_line or b"HTTP/1.0 200" in first_line):
                s.close()
                last_fail = "PROXY_REJECTED"
                continue

            # Full TLS handshake and System CA certificate verification
            ss = ssl_ctx.wrap_socket(s, server_hostname=t)
            ss.settimeout(timeout)
            ss.do_handshake()
            cert = ss.getpeercert()
            ss.close()
            # Successfully passed TLS handshake & verified CA
            return entry, True, "SURVIVOR"

        except ssl.SSLCertVerificationError as e:
            if ss:
                try: ss.close()
                except Exception: pass
            elif s:
                try: s.close()
                except Exception: pass
            return entry, False, "CERT_VALIDATION_FAIL"

        except (socket.timeout, TimeoutError):
            last_fail = "TIMEOUT"
        except (ConnectionRefusedError, ConnectionResetError):
            last_fail = "CONN_REFUSED_OR_RESET"
        except ssl.SSLEOFError:
            last_fail = "SSL_EOF"
        except ssl.SSLError:
            last_fail = "SSL_ERROR"
        except Exception as e:
            last_fail = f"OTHER_{type(e).__name__}"
        finally:
            if ss:
                try: ss.close()
                except Exception: pass
            elif s:
                try: s.close()
                except Exception: pass

    return entry, False, last_fail

def main():
    pool_file = r"D:\DEpinFarm\ip\harvest\real_pool.txt"
    backup_file = r"D:\DEpinFarm\ip\harvest\real_pool_backup_pre_strict.txt"
    
    with open(pool_file, "r", encoding="utf-8") as f:
        entries = [l.strip() for l in f if l.strip()]

    print(f"Starting Strict Re-verification of all {len(entries):,} proxies in real_pool.txt...")
    print("Probe requirement: Complete TLS handshake + System CA chain validation")
    
    shutil.copy2(pool_file, backup_file)
    print(f"Backup saved to {backup_file}")

    t0 = time.time()
    survivors = []
    stats = {
        "SURVIVOR": 0,
        "CERT_VALIDATION_FAIL": 0,
        "TIMEOUT": 0,
        "PROXY_REJECTED": 0,
        "CONN_REFUSED_OR_RESET": 0,
        "SSL_EOF": 0,
        "SSL_ERROR": 0,
        "OTHER": 0
    }

    done = 0
    total = len(entries)
    with ThreadPoolExecutor(max_workers=120) as ex:
        for entry, ok, reason in ex.map(probe_strict, entries):
            done += 1
            if ok:
                survivors.append(entry)
                stats["SURVIVOR"] += 1
            else:
                if reason in stats:
                    stats[reason] += 1
                else:
                    stats["OTHER"] += 1

            if done % 1000 == 0 or done == total:
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                print(f"[{done:,}/{total:,}] Checked ({rate:.1f} prx/s) | Survivors: {stats['SURVIVOR']:,} | Cert Fails: {stats['CERT_VALIDATION_FAIL']:,}", flush=True)

    elapsed_total = time.time() - t0

    # Write cleaned survivors back to real_pool.txt
    with open(pool_file, "w", encoding="utf-8") as f:
        for s in survivors:
            f.write(f"{s}\n")

    print("\n" + "="*70)
    print("STRICT RE-VERIFICATION COMPLETE")
    print("="*70)
    print(f"Total Proxies Checked        : {total:,}")
    print(f"Genuine TLS Survivors (Saved): {len(survivors):,} ({len(survivors)/total*100:.2f}%)")
    print(f"Elapsed Time                 : {elapsed_total:.1f}s ({total/elapsed_total:.1f} proxies/s)")
    print("\nFAILURE BREAKDOWN:")
    print(f"  * Failed on CERT VALIDATION (MITM / Self-Signed): {stats['CERT_VALIDATION_FAIL']:,} ({stats['CERT_VALIDATION_FAIL']/total*100:.2f}%)")
    print(f"  * Failed on TIMEOUT                             : {stats['TIMEOUT']:,} ({stats['TIMEOUT']/total*100:.2f}%)")
    print(f"  * Failed on PROXY_REJECTED (non-200)            : {stats['PROXY_REJECTED']:,} ({stats['PROXY_REJECTED']/total*100:.2f}%)")
    print(f"  * Failed on CONN_REFUSED_OR_RESET               : {stats['CONN_REFUSED_OR_RESET']:,} ({stats['CONN_REFUSED_OR_RESET']/total*100:.2f}%)")
    print(f"  * Failed on SSL_EOF / SSL_ERROR                 : {stats['SSL_EOF'] + stats['SSL_ERROR']:,} ({(stats['SSL_EOF'] + stats['SSL_ERROR'])/total*100:.2f}%)")
    print(f"  * Failed on OTHER                               : {stats['OTHER']:,} ({stats['OTHER']/total*100:.2f}%)")
    print("="*70)

if __name__ == "__main__":
    main()
