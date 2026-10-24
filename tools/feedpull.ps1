$ErrorActionPreference = 'Continue'
$root = 'D:\DEpinFarm'
$out  = Join-Path $root 'ip\harvest\feeds_raw.txt'
$log  = Join-Path $root 'work\feedpull.log'
New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null

$feeds = @(
  # monosans
  'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/all.txt',
  'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt',
  'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt',
  'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt',
  'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_anonymous/all.txt',
  'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_geolocation/all.txt',

  # TheSpeedX
  'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt',
  'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt',
  'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt',

  # proxifly
  'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt',
  'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks4/data.txt',
  'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt',
  'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.json',

  # ObcbO
  'https://raw.githubusercontent.com/ObcbO/getproxy/master/file/http.txt',
  'https://raw.githubusercontent.com/ObcbO/getproxy/master/file/https.txt',
  'https://raw.githubusercontent.com/ObcbO/getproxy/master/file/socks4.txt',
  'https://raw.githubusercontent.com/ObcbO/getproxy/master/file/socks5.txt',

  # MuRongPIG
  'https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/http.txt',
  'https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks4.txt',
  'https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks5.txt',

  # zevtyardt
  'https://raw.githubusercontent.com/zevtyardt/proxy-list/main/all.txt',

  # hookzof
  'https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt',

  # Anonym0usWork1221
  'https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/master/proxy_files/http_proxies.txt',
  'https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/master/proxy_files/https_proxies.txt',
  'https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/master/proxy_files/socks4_proxies.txt',
  'https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/master/proxy_files/socks5_proxies.txt',

  # ProxyScraper
  'https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/http.txt',
  'https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/socks4.txt',
  'https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/socks5.txt',

  # ShiftyTR
  'https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt',
  'https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt',
  'https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks4.txt',
  'https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt',

  # roosterkid
  'https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt',
  'https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS4_RAW.txt',
  'https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt',

  # zloi-user
  'https://raw.githubusercontent.com/zloi-user/hideip.me/main/http.txt',
  'https://raw.githubusercontent.com/zloi-user/hideip.me/main/https.txt',
  'https://raw.githubusercontent.com/zloi-user/hideip.me/main/socks4.txt',
  'https://raw.githubusercontent.com/zloi-user/hideip.me/main/socks5.txt',

  # vakhov
  'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt',
  'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/https.txt',
  'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks4.txt',
  'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt',

  # jetkai
  'https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt',
  'https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-https.txt',
  'https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks4.txt',
  'https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt',

  # casals-ar
  'https://raw.githubusercontent.com/casals-ar/proxy-list/main/https',
  'https://raw.githubusercontent.com/casals-ar/proxy-list/main/socks4',
  'https://raw.githubusercontent.com/casals-ar/proxy-list/main/socks5',

  # proxyspace
  'https://proxyspace.pro/http.txt',
  'https://proxyspace.pro/https.txt',
  'https://proxyspace.pro/socks4.txt',
  'https://proxyspace.pro/socks5.txt',

  # spys.me
  'https://spys.me/proxy.txt',
  'https://spys.me/socks.txt',

  # ALIILAPRO
  'https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/http.txt',
  'https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/socks4.txt',
  'https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/socks5.txt',

  # rdavydov
  'https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/http.txt',
  'https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/socks4.txt',
  'https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/socks5.txt',

  # Zaeem20
  'https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/http.txt',
  'https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/https.txt',
  'https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks4.txt',
  'https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks5.txt',

  # clarketm
  'https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt',

  # hendrikbgr
  'https://raw.githubusercontent.com/hendrikbgr/Free-Proxy-Repo/master/proxy_list.txt',

  # almroot
  'https://raw.githubusercontent.com/almroot/proxylist/master/list.txt',

  # mmpx12
  'https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt',
  'https://raw.githubusercontent.com/mmpx12/proxy-list/master/https.txt',
  'https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks4.txt',
  'https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5.txt'
)

$seen = New-Object 'System.Collections.Generic.HashSet[string]'
$rep  = @()
$rep += 'RUN ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')

foreach ($u in $feeds) {
  $parts = $u -split '/'
  $tag = if ($parts.Length -ge 5) { $parts[3] + '/' + $parts[4] + '/' + $parts[-1] } else { $u }
  try {
    $req = [System.Net.HttpWebRequest]::Create($u)
    $req.Timeout = 15000
    $req.UserAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    $resp = $req.GetResponse()
    $stream = $resp.GetResponseStream()
    $reader = New-Object System.IO.StreamReader($stream)
    $txt = $reader.ReadToEnd()
    $reader.Close()
    $resp.Close()
  } catch {
    $rep += 'FAIL  ' + $tag + '  ' + $_.Exception.Message
    continue
  }

  $before = $seen.Count
  if ($u -match '\.json$') {
    try {
      $j = $txt | ConvertFrom-Json
      foreach ($e in $j) {
        if ($e.ip -and $e.port) { [void]$seen.Add($e.ip + ':' + $e.port) }
      }
    } catch { $rep += 'JSONERR ' + $tag; continue }
  } else {
    $matches = [regex]::Matches($txt, '(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})')
    foreach ($m in $matches) {
      [void]$seen.Add($m.Groups[1].Value + ':' + $m.Groups[2].Value)
    }
  }
  $rep += ('OK    {0,-35}  new={1,6}  total={2,7}' -f $tag, ($seen.Count - $before), $seen.Count)
}

$seen | Set-Content -Path $out -Encoding ascii
$rep += 'TOTAL_UNIQUE=' + $seen.Count
$rep | Tee-Object -FilePath $log -Append
Write-Host ''
Write-Host ('WROTE {0} rows to {1}' -f $seen.Count, $out)
