#!/usr/bin/env bash
set -uo pipefail
touch ip/public_pool.txt
cat ip/harvest/results/*.txt 2>/dev/null | sort -u > ip/harvest/survivors.txt
cat ip/master_pool.txt ip/public_pool.txt 2>/dev/null | grep -Eo '([0-9]{1,3}\.){3}[0-9]{1,3}' | sort -u > ip/harvest/seen.txt
awk -F'\t' 'NR==FNR{s[$1]=1;next}{split($1,a,":");ip=a[1];if(!(ip in s)&&!(ip in a2)){print; a2[ip]=1}}' \
  ip/harvest/seen.txt ip/harvest/survivors.txt > ip/harvest/new.txt
cat ip/harvest/new.txt >> ip/public_pool.txt
echo "survivors: $(wc -l < ip/harvest/survivors.txt)"
echo "new added: $(wc -l < ip/harvest/new.txt)"
echo "public_pool total: $(wc -l < ip/public_pool.txt)"
