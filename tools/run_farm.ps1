$root = "D:\DEpinFarm"
$ROUNDS = 28
function L($m){ "$(Get-Date -f 'yyyy-MM-dd HH:mm:ss') $m" | Add-Content "$root\work\farm.log" }

$accounts = @(
  @{a='acct1'; u='lalthazualasailo'; k=@('a','b','g','h','i')},
  @{a='acct2'; u='zomuanpuia';       k=@('c','d','j','k','l')},
  @{a='acct3'; u='laldinthari';      k=@('e','f','m','n','o')},
  @{a='acct4'; u='lalsangkima';      k=@('p','q','r','s','t')},
  @{a='acct6'; u='spectatorlone';    k=@('u','v','w','x','y')},
  @{a='acct5'; u='remruata';         k=@('verify','merge','z','aa')}
)

$round = [int](Get-Content "$root\work\round.txt")
if ($round -ge $ROUNDS) { L "ALL_ROUNDS_DONE round=$round"; exit }

foreach ($acct in $accounts) {
  $env:KAGGLE_API_TOKEN = (Get-Content "$root\kaggle\$($acct.a)\access_token" -Raw).Trim()
  foreach ($letter in $acct.k) {
    $slug = "$($acct.u)/ipscan-cl-$letter"
    $st = (kaggle kernels status $slug 2>&1 | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($st)) {
      Start-Sleep -Seconds 3
      $st = (kaggle kernels status $slug 2>&1 | Out-String).Trim()
    }
    if ([string]::IsNullOrWhiteSpace($st)) {
      L "SKIP $slug (empty status after retry)"
      continue
    }

    $raw = $st -replace '[\r\n]+', ' '

    # GUARD: NEVER push on rate limit (429)
    if ($st -match '429|Too Many Requests') {
      L "SKIP $slug (429 rate limit)"
      continue
    }

    # GUARD: NEVER push a running or queued kernel (prevents zombie + slot burn)
    if ($st -match 'RUNNING|QUEUED') {
      L "SKIP $slug (RUNNING/QUEUED: $raw)"
      continue
    }

    # Only push if COMPLETE, absent (404/not found), ERROR, or CANCELLED
    if ($st -notmatch 'COMPLETE|ERROR|CANCEL|FAILED|CANCEL_ACKNOWLEDGED|404|not found') {
      L "SKIP $slug ($raw)"
      continue
    }

    kaggle kernels push -p "$root\kaggle\cl_$letter" | Out-Null
    L "PUSHED $slug round=$round (was $raw)"
    Start-Sleep -Seconds 25
  }
}
