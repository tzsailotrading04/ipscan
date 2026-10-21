#!/usr/bin/env bash
set -uo pipefail
mkdir -p ip/harvest/raw ip/harvest/shards
: > ip/harvest/raw/plain.txt
: > ip/harvest/raw/html.txt

grab() {
  local n="$1" u="$2" p=http
  case "$n" in *socks5*) p=socks5 ;; *socks4*) p=socks4 ;; esac
  curl -fsSL --max-time 45 "$u" 2>/dev/null \
    | grep -Eo '([0-9]{1,3}\.){3}[0-9]{1,3}:[0-9]{1,5}' \
    | sed "s|^|$p://|" >> ip/harvest/raw/plain.txt || true
}
grabhtml() {
  curl -fsSL --max-time 45 "$1" 2>/dev/null | sed 's/<[^>]*>/ /g' \
    | grep -Eo '([0-9]{1,3}\.){3}[0-9]{1,3}[[:space:]]+[0-9]{1,5}' \
    | tr -s ' ' | tr ' ' ':' | sed 's|^|http://|' >> ip/harvest/raw/html.txt || true
}

B=https://raw.githubusercontent.com
grab monosans_http      $B/monosans/proxy-list/main/proxies/http.txt
grab monosans_socks4    $B/monosans/proxy-list/main/proxies/socks4.txt
grab monosans_socks5    $B/monosans/proxy-list/main/proxies/socks5.txt
grab speedx_http        $B/TheSpeedX/PROXY-List/master/http.txt
grab speedx_socks4      $B/TheSpeedX/PROXY-List/master/socks4.txt
grab speedx_socks5      $B/TheSpeedX/PROXY-List/master/socks5.txt
grab rooster_https      $B/roosterkid/openproxylist/main/HTTPS_RAW.txt
grab rooster_socks4     $B/roosterkid/openproxylist/main/SOCKS4_RAW.txt
grab rooster_socks5     $B/roosterkid/openproxylist/main/SOCKS5_RAW.txt
grab shifty_http        $B/ShiftyTR/Proxy-List/master/http.txt
grab shifty_socks4      $B/ShiftyTR/Proxy-List/master/socks4.txt
grab shifty_socks5      $B/ShiftyTR/Proxy-List/master/socks5.txt
grab clarketm           $B/clarketm/proxy-list/master/proxy-list-raw.txt
grab hookzof_socks5     $B/hookzof/socks5_list/master/proxy.txt
grab mmpx12_http        $B/mmpx12/proxy-list/master/http.txt
grab mmpx12_https       $B/mmpx12/proxy-list/master/https.txt
grab mmpx12_socks4      $B/mmpx12/proxy-list/master/socks4.txt
grab mmpx12_socks5      $B/mmpx12/proxy-list/master/socks5.txt
grab sunny_proxies      $B/sunny9577/proxy-scraper/master/proxies.txt
grab jetkai_http        $B/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt
grab jetkai_https       $B/jetkai/proxy-list/main/online-proxies/txt/proxies-https.txt
grab jetkai_socks4      $B/jetkai/proxy-list/main/online-proxies/txt/proxies-socks4.txt
grab jetkai_socks5      $B/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt
grab murongpig_http     $B/MuRongPIG/Proxy-Master/main/http.txt
grab murongpig_socks4   $B/MuRongPIG/Proxy-Master/main/socks4.txt
grab murongpig_socks5   $B/MuRongPIG/Proxy-Master/main/socks5.txt
grab aliilapro_http     $B/ALIILAPRO/Proxy/main/http.txt
grab aliilapro_socks4   $B/ALIILAPRO/Proxy/main/socks4.txt
grab aliilapro_socks5   $B/ALIILAPRO/Proxy/main/socks5.txt
grab prxchk_http        $B/prxchk/proxy-list/main/http.txt
grab prxchk_socks5      $B/prxchk/proxy-list/main/socks5.txt
grab anonym0us_http     $B/Anonym0usWork1221/Free-Proxies/main/proxy_files/http_proxies.txt
grab anonym0us_socks5   $B/Anonym0usWork1221/Free-Proxies/main/proxy_files/socks5_proxies.txt
grab hideip_http        $B/zloi-user/hideip.me/main/http.txt
grab hideip_socks5      $B/zloi-user/hideip.me/main/socks5.txt
grab tuanminpay_socks5  $B/TuanMinPay/live-proxy/main/socks5.txt
grab kangproxy_http     $B/KangProxy/KangProxy.github.io/master/http.txt
grab kangproxy_socks5   $B/KangProxy/KangProxy.github.io/master/socks5.txt
grab proxyscrape_v2     "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all"
grab proxyscrape_v4     "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=http&proxy_format=ipport&format=text"
grab proxylistdl_http   "https://www.proxy-list.download/api/v1/get?type=http"
grab proxylistdl_socks5 "https://www.proxy-list.download/api/v1/get?type=socks5"
grab openproxy_http     "https://openproxy.space/list/http"
grab openproxy_socks5   "https://openproxy.space/list/socks5"
grabhtml "https://free-proxy-list.net/"
grabhtml "https://www.sslproxies.org/"
grabhtml "https://www.us-proxy.org/"
grabhtml "https://www.socks-proxy.net/"

cat ip/harvest/raw/plain.txt ip/harvest/raw/html.txt | sort -u > ip/harvest/all.txt
rm -f ip/harvest/shards/*.txt
split -n l/60 -d --additional-suffix=.txt ip/harvest/all.txt ip/harvest/shards/shard_
echo "total candidates: $(wc -l < ip/harvest/all.txt)"
