# D:\DEpinFarm\tools\fleet_guard.ps1
# DepinFarm Fleet Guard (v98.117)
$ErrorActionPreference = "Continue"
$root = "D:\DEpinFarm"
Set-Location $root
$logFile = "$root\tools\fleet_guard.log"
$EXPECT = if (Test-Path "work/VERSION") { (Get-Content "work/VERSION" -Raw).Trim() } else { "v98.143" }
$STOPPED = Test-Path "work/STOP_SHODAN"

function Log-Msg($msg) {
    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $line = "[$ts] [GUARD] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding utf8
}

Log-Msg "=== Fleet Guard check started (expected: $EXPECT) ==="

try {
    git -C $root fetch origin main --quiet 2>&1 | Out-Null
} catch {
    Log-Msg "Git fetch failed: $_"
}

$map = [ordered]@{
    "acct5" = @("shodan_00","shodan_01")
    "acct1" = @("shodan_02","shodan_03","shodan_04","shodan_05")
    "acct2" = @("shodan_06","shodan_07","shodan_08","shodan_09")
    "acct3" = @("shodan_10","shodan_11","shodan_12","shodan_13")
    "acct4" = @("shodan_14","shodan_15","shodan_16","shodan_17")
    "acct6" = @("shodan_18","shodan_19")
    # Shards 32 and 33 permanently removed from revive list to free 2 slots on stephen34
    "stephen34" = @("shodan_29","shodan_30","shodan_31")
}

$healthyCount = 0
$restartedCount = 0

foreach ($acct in $map.Keys) {
    $tokPath = "$root\kaggle\$acct\access_token"
    if (-not (Test-Path $tokPath)) { continue }
    $env:KAGGLE_API_TOKEN = (Get-Content $tokPath -Raw).Trim()

    foreach ($s in $map[$acct]) {
        $metaPath = "$root\kaggle\cl_$s\kernel-metadata.json"
        if (-not (Test-Path $metaPath)) { continue }
        $meta = Get-Content $metaPath -Raw | ConvertFrom-Json
        $kid = $meta.id

        # Check Kaggle status
        $statusOut = (kaggle kernels status $kid 2>&1 | Out-String).Trim()
        $kStatus = "UNKNOWN"
        foreach ($line in $statusOut -split "`n") {
            if ($line -match 'status "([^"]+)"') { $kStatus = $matches[1] }
            elseif ($line -match 'status ([a-zA-Z0-9_\.]+)') { $kStatus = $matches[1] }
        }

        # Check git stats
        $statsTag = $s -replace "shodan_",""
        $rawStats = git -C $root show "origin/main:ip/harvest/shodan_stats_v98_$statsTag.txt" 2>&1 | Out-String
        $stats = @{}
        foreach ($line in $rawStats -split "`n") {
            if ($line -match '^\s*([^=]+)=(.*)$') {
                $stats[$matches[1].Trim()] = $matches[2].Trim()
            }
        }

        $engine = $stats["engine"]
        $rolling429 = [double]($stats["rolling_429"] -as [double])
        $offset = $stats["offset"]

        $needsRestart = $false
        if (-not $STOPPED -and ($kStatus -match "COMPLETE|ERROR|CANCELLED")) {
            Log-Msg "Shard $s ($kid) is $kStatus"
            $needsRestart = $true
        } elseif (-not $STOPPED -and $engine -and $engine -ne $EXPECT) {
            Log-Msg "Shard $s has engine=$engine (expected $EXPECT)"
            $needsRestart = $true
        }

        if ($needsRestart) {
            Log-Msg "Restarting $s as $acct..."
            $pushed = $false
            for ($t = 1; $t -le 3; $t++) {
                $pushOut = (kaggle kernels push -p "$root\kaggle\cl_$s" 2>&1 | Out-String).Trim()
                if ($pushOut -match "409|Conflict") { Start-Sleep 5; continue }
                $pushed = $true
                break
            }
            if ($pushed) {
                Log-Msg "Re-pushed cl_$($s) successfully."
                $restartedCount++
            } else {
                Log-Msg "Failed to re-push cl_$($s): $pushOut"
            }
            Start-Sleep 3
        } else {
            $healthyCount++
            Log-Msg "Shard $($s): status=$kStatus engine=$engine offset=$offset 429=$($rolling429)%"
        }
    }
}

# Check and revive all 9 verifier kernels (cl_verify_0 .. cl_verify_8)
$vmap = [ordered]@{
    "acct1" = @("verify_0")
    "acct2" = @("verify_1")
    "acct3" = @("verify_2")
    "acct4" = @("verify_3")
    "acct5" = @("verify_4","verify_5","verify_6")
    "acct6" = @("verify_7","verify_8")
}

foreach ($vk in $vmap.Keys) {
    $vAcct = $vmap[$vk]
    $vTokPath = "$root\kaggle\$vAcct\access_token"
    if (-not (Test-Path $vTokPath)) { continue }
    $env:KAGGLE_API_TOKEN = (Get-Content $vTokPath -Raw).Trim()

    $vDir = "$root\kaggle\cl_verify_$vk"
    $vMetaPath = "$vDir\kernel-metadata.json"
    if (-not (Test-Path $vMetaPath)) { continue }
    $vMeta = Get-Content $vMetaPath -Raw | ConvertFrom-Json
    $vkid = $vMeta.id

    $vStatusOut = (kaggle kernels status $vkid 2>&1 | Out-String).Trim()
    $vkStatus = "UNKNOWN"
    foreach ($line in $vStatusOut -split "`n") {
        if ($line -match 'status "([^"]+)"') { $vkStatus = $matches[1] }
        elseif ($line -match 'status ([a-zA-Z0-9_\.]+)') { $vkStatus = $matches[1] }
    }
    if (-not $STOPPED -and ($vkStatus -match "COMPLETE|ERROR|CANCELLED")) {
        Log-Msg "Verifier cl_verify_$vk ($vkid) is $vkStatus, reviving..."
        $pushed = $false
        for ($t = 1; $t -le 3; $t++) {
            $pushOut = (kaggle kernels push -p $vDir 2>&1 | Out-String).Trim()
            if ($pushOut -match "409|Conflict") { Start-Sleep 5; continue }
            $pushed = $true
            break
        }
        if ($pushed) {
            Log-Msg "Re-pushed cl_verify_$vk successfully."
            $restartedCount++
        } else {
            Log-Msg "Failed to re-push cl_verify_$vk : $pushOut"
        }
        Start-Sleep 3
    } else {
        Log-Msg "Verifier cl_verify_${vk}: status=$vkStatus"
    }
}

# -------------------------------------------------------------
# Local Daemons & Tasks Supervision: fleet_cycle, pool_reverify, dead_recycle
# -------------------------------------------------------------
$cooldownSec = 120  # Two-minute cooldown check

function Test-Cooldown($lockFile) {
    if (Test-Path $lockFile) {
        $last = (Get-Item $lockFile).LastWriteTime
        if ((Get-Date) - $last -lt (New-TimeSpan -Seconds $cooldownSec)) {
            return $false
        }
    }
    return $true
}

# 1. fleet_cycle.py
$fcProc = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*fleet_cycle.py*" }
if (-not $fcProc) {
    $fcLock = "$root\work\fleet_cycle_guard.lck"
    if (Test-Cooldown $fcLock) {
        Log-Msg "fleet_cycle.py not running. Starting in background..."
        Set-Content -Path $fcLock -Value (Get-Date).ToString()
        Start-Process -FilePath "python" -ArgumentList "tools\fleet_cycle.py" -WorkingDirectory $root -WindowStyle Hidden
    } else {
        Log-Msg "fleet_cycle.py in cooldown; skipping restart."
    }
} else {
    Log-Msg "fleet_cycle.py running (PID: $($fcProc.ProcessId))."
}

# 2. pool_reverify.py
$prProc = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*pool_reverify.py*" }
if (-not $prProc) {
    $prLock = "$root\work\pool_reverify_guard.lck"
    if (Test-Cooldown $prLock) {
        Log-Msg "pool_reverify.py not running. Starting in background..."
        Set-Content -Path $prLock -Value (Get-Date).ToString()
        Start-Process -FilePath "python" -ArgumentList "tools\pool_reverify.py" -WorkingDirectory $root -WindowStyle Hidden
    } else {
        Log-Msg "pool_reverify.py in cooldown; skipping restart."
    }
} else {
    Log-Msg "pool_reverify.py running (PID: $($prProc.ProcessId))."
}

# 3. dead_recycle.py (every 6 hours)
$drLastRunFile = "$root\work\dead_recycle_last_run.txt"
$drLock = "$root\work\dead_recycle_guard.lck"
$drProc = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*dead_recycle.py*" }
$sixHoursSec = 6 * 3600

$shouldRunDeadRecycle = $false
if (-not $drProc) {
    if (-not (Test-Path $drLastRunFile)) {
        $shouldRunDeadRecycle = $true
    } else {
        $lastRunTime = (Get-Item $drLastRunFile).LastWriteTime
        if ((Get-Date) - $lastRunTime -ge (New-TimeSpan -Seconds $sixHoursSec)) {
            $shouldRunDeadRecycle = $true
        }
    }
}

if ($shouldRunDeadRecycle) {
    if (Test-Cooldown $drLock) {
        Log-Msg "dead_recycle.py due (6-hour interval reached). Starting pass..."
        Set-Content -Path $drLock -Value (Get-Date).ToString()
        Start-Process -FilePath "python" -ArgumentList "tools\dead_recycle.py --once" -WorkingDirectory $root -WindowStyle Hidden
    } else {
        Log-Msg "dead_recycle.py in cooldown; skipping run."
    }
} else {
    if ($drProc) {
        Log-Msg "dead_recycle.py currently running (PID: $($drProc.ProcessId))."
    } else {
        Log-Msg "dead_recycle.py interval not reached (runs every 6h)."
    }
}

Log-Msg "=== Guard check complete. Healthy: $healthyCount/20, Restarted: $restartedCount ==="
