# D:\DEpinFarm\tools\fleet_guard.ps1
# DepinFarm Fleet Guard (v98.117)
$ErrorActionPreference = "Continue"
$root = "D:\DEpinFarm"
Set-Location $root
$logFile = "$root\tools\fleet_guard.log"
$EXPECT = if (Test-Path "work/VERSION") { (Get-Content "work/VERSION" -Raw).Trim() } else { "v98.114" }
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
    0 = "acct6"
    1 = "acct6"
    2 = "acct6"
    3 = "acct5"
    4 = "acct5"
    5 = "acct5"
    6 = "acct6"
    7 = "acct5"
    8 = "acct6"
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
        Log-Msg "Verifier cl_verify_$vk: status=$vkStatus"
    }
}

Log-Msg "=== Guard check complete. Healthy: $healthyCount/20, Restarted: $restartedCount ==="
