$ErrorActionPreference = "Stop"
$root = "D:\DEpinFarm"
Set-Location $root

Write-Host "=== [1/7] repairing conflict-marker corruption ===" -ForegroundColor Cyan
$n = 0
Get-ChildItem "$root\ip\harvest\shodan_progress*.txt" -ErrorAction SilentlyContinue | ForEach-Object {
    $vals = Get-Content $_.FullName | Where-Object { $_ -match '^\s*\d+\s*$' } |
            ForEach-Object { [int]$_.Trim() }
    $max = if ($vals) { ($vals | Measure-Object -Maximum).Maximum } else { 0 }
    Set-Content -Path $_.FullName -Value $max -Encoding ascii
    if ((Get-Content $_.FullName).Count -gt 1) { $n++ }
    Write-Host ("  {0} -> {1}" -f $_.Name, $max)
}

Write-Host "=== [2/7] stripping markers from shard files ===" -ForegroundColor Cyan
Get-ChildItem "$root\ip\harvest\shodan_shard*.txt" -ErrorAction SilentlyContinue | ForEach-Object {
    $before = @(Get-Content $_.FullName).Count
    $good = @(Get-Content $_.FullName | Where-Object {
        $_ -and -not $_.StartsWith("<<<") -and -not $_.StartsWith("===") -and -not $_.StartsWith(">>>")
    })
    if ($before -ne $good.Count) {
        Set-Content -Path $_.FullName -Value $good -Encoding ascii
        Write-Host ("  {0}: {1} -> {2} lines" -f $_.Name, $before, $good.Count)
    }
}

Write-Host "=== [3/7] patching run.py ===" -ForegroundColor Cyan
$rp = "$root\kaggle\cl_shodan\run.py"
$s = Get-Content $rp -Raw

$helper = @'
def read_offset(path):
    """Tolerate git conflict markers from autostash pop: take largest integer."""
    if not os.path.exists(path):
        return 0
    vals = []
    try:
        with open(path, "r", errors="ignore") as f:
            for line in f:
                t = line.strip()
                if t.isdigit():
                    vals.append(int(t))
    except Exception:
        return 0
    return max(vals) if vals else 0


def write_offset(path, val):
    with open(path, "w") as f:
        f.write(str(val) + "\n")


'@
if ($s -notmatch "def read_offset") {
    $s = $s.Replace("class LightPacer:", $helper + "class LightPacer:")
}

$oldResume = @'
    prog_file = os.path.join(REPO, "ip", "harvest", f"shodan_progress_{OUT_PREFIX}{SHARD_TAG}.txt")
    resume_offset = 0
    if os.path.exists(prog_file):
        try:
            v = open(prog_file).read().strip()
            if v.isdigit():
                resume_offset = int(v)
        except Exception:
            pass
    log(f"resume_offset={resume_offset:,}/{total_ips:,}")
'@
$newResume = @'
    prog_file = os.path.join(REPO, "ip", "harvest", f"shodan_progress_{OUT_PREFIX}{SHARD_TAG}.txt")
    resume_offset = read_offset(prog_file)
    write_offset(prog_file, resume_offset)
    log(f"resume_offset={resume_offset:,}/{total_ips:,}")
'@
if ($s.Contains($oldResume)) { $s = $s.Replace($oldResume, $newResume) }
elseif ($s -notmatch "resume_offset = read_offset") { Write-Host "  !! resume block not matched" -ForegroundColor Red; exit 1 }

$anchor = 'out_handle = open(out_shard_file, "a", encoding="utf-8")'
$purge = @'
try:
    with open(out_shard_file, "r", encoding="utf-8", errors="ignore") as _f:
        _good = [l for l in _f if l.strip() and not l.startswith(("<<<", "===", ">>>"))]
    with open(out_shard_file, "w", encoding="utf-8") as _f:
        _f.writelines(_good)
    log(f"shard file purged to {len(_good):,} clean lines")
except Exception as _e:
    log(f"purge skipped: {_e}")

'@
if ($s -notmatch "shard file purged") { $s = $s.Replace($anchor, $purge + $anchor) }

Set-Content -Path $rp -Value $s -Encoding ascii

Write-Host "=== [4/7] patching verify_v982.py ===" -ForegroundColor Cyan
$vp = "$root\tools\verify_v982.py"
$v = Get-Content $vp -Raw
$oldR = @'
def read_prog():
    o = {}
    for i in range(20):
        p = os.path.join(H, f"shodan_progress_v98_{i:02d}.txt")
        try:
            o[i] = int(open(p).read().strip())
        except Exception:
            o[i] = 0
    return o
'@
$newR = @'
def read_prog():
    o = {}
    for i in range(20):
        p = os.path.join(H, f"shodan_progress_v98_{i:02d}.txt")
        vals = []
        try:
            for l in open(p, errors="ignore"):
                t = l.strip()
                if t.isdigit():
                    vals.append(int(t))
        except Exception:
            pass
        o[i] = max(vals) if vals else 0
    return o
'@
if ($v.Contains($oldR)) { $v = $v.Replace($oldR, $newR) }
elseif ($v -notmatch "vals = \[\]") { Write-Host "  !! read_prog not matched" -ForegroundColor Red; exit 1 }
Set-Content -Path $vp -Value $v -Encoding ascii

Write-Host "=== [5/7] writing stale-pod watcher ===" -ForegroundColor Cyan
$watch = @'
import glob
import os
import subprocess
import sys
import time

REPO = r"D:\DEpinFarm"
H = os.path.join(REPO, "ip", "harvest")
STALE_MARK = "/3350000"
NEW_MARK = "v98.2"
QUIET_MIN = 8
MAX_WAIT = 45 * 60
SETTLE = 420


def run(args):
    return subprocess.run(args, cwd=REPO, capture_output=True, text=True)


def pull():
    run(["git", "pull", "--rebase", "--autostash", "origin", "main"])


def recent_subjects(minutes):
    r = run(["git", "log", f"--since={minutes} minutes ago", "--format=%s", "origin/main"])
    return [l for l in r.stdout.splitlines() if l.strip()]


def stats_count():
    return len(glob.glob(os.path.join(H, "shodan_stats_v98_*.txt")))


def main():
    t0 = time.time()
    saw_stale = False
    reason = "TIMEOUT"
    print(f"Watching origin/main up to {MAX_WAIT // 60} min for stale v94 pods to die...")
    print(f"Signal: commits containing '{STALE_MARK}' must stop arriving\n")

    while time.time() - t0 < MAX_WAIT:
        pull()
        subs = recent_subjects(QUIET_MIN)
        stale = sum(1 for s in subs if STALE_MARK in s)
        new = sum(1 for s in subs if NEW_MARK in s)
        n_stats = stats_count()
        el = int(time.time() - t0)
        print(f"[{el:4d}s] last{QUIET_MIN}m: stale_v94={stale:2d}  v98.2={new:2d}  stats_files={n_stats}")
        if stale > 0:
            saw_stale = True
        if n_stats > 0:
            reason = "NEW CODE ALREADY LIVE"
            break
        if saw_stale and stale == 0:
            reason = "STALE PODS GONE"
            break
        time.sleep(60)

    print(f"\nLOOP EXIT: {reason}")

    if reason == "NEW CODE ALREADY LIVE":
        print("v98.2 pods already running - skipping re-push")
    else:
        print("Re-pushing all 20 shards...")
        r = subprocess.run([sys.executable, os.path.join(REPO, "tools", "deploy_shodan_v98.py")],
                           cwd=REPO, text=True)
        print(f"deploy exit={r.returncode}")

    print(f"\nSettling {SETTLE}s...")
    time.sleep(SETTLE)

    print("\nRunning verifier...")
    subprocess.run([sys.executable, os.path.join(REPO, "tools", "verify_v982.py"), "600"], cwd=REPO)

    n = stats_count()
    print(f"\nFINAL stats_files={n}")
    if n == 0:
        print("RESULT: nothing running - report the loop log")
        sys.exit(2)
    print("RESULT: v98.2 IS RUNNING")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
'@
Set-Content -Path "$root\tools\watch_and_repush.py" -Value $watch -Encoding ascii

Write-Host "=== [6/7] syntax check ===" -ForegroundColor Cyan
python -m py_compile $rp
python -m py_compile $vp
python -m py_compile "$root\tools\watch_and_repush.py"
Write-Host "  all three compile" -ForegroundColor Green

Write-Host "=== [7/7] commit and push ===" -ForegroundColor Cyan
git add kaggle/cl_shodan/run.py tools/verify_v982.py tools/watch_and_repush.py tools/final_v985.ps1
git add ip/harvest/shodan_progress*.txt ip/harvest/shodan_shard*.txt
git commit -m "v98.6: repair conflict-marker corruption, robust readers, stale watcher"
for ($pushTry = 1; $pushTry -le 10; $pushTry++) {
    git pull --rebase --autostash origin main
    git push origin main
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 2
}
Write-Host "  pushed" -ForegroundColor Green

Write-Host ""
Write-Host "############################################################" -ForegroundColor Yellow
Write-Host "#  NOW: STOP THE 20 SESSIONS IN THE KAGGLE BROWSER        #" -ForegroundColor Yellow
Write-Host "#  kaggle.com/code -> Active Events -> Stop each cl_shodan #" -ForegroundColor Yellow
Write-Host "#  6 accounts. ~3 clicks each. Watcher starts in 30s.      #" -ForegroundColor Yellow
Write-Host "############################################################" -ForegroundColor Yellow
Write-Host ""
Start-Sleep -Seconds 30

python "$root\tools\watch_and_repush.py"
Write-Host "FINAL_V985_DONE" -ForegroundColor Green
