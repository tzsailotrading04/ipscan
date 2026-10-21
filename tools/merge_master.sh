#!/usr/bin/env bash
set -e

# tools/merge_master.sh - Master pool merger
# Concatenates and deduplicates all discovered proxy pools by exit IP.
# Generates master_pool.txt, master_fast.txt, and master_summary.txt.

ROOT_DIR="${1:-.}"
cd "$ROOT_DIR"

TMP_DIR=$(mktemp -d 2>/dev/null || mktemp -d -t 'mastermerge')
trap 'rm -rf "$TMP_DIR"' EXIT

echo "=== Master Merge Starting ==="
echo "Scanning for pool files under $(pwd) ..."

# Collect pools and tag their origin
# Format in tagged file: <origin> <ip:port> <exit_ip> <ttfb_ms> <kbps>
TAGGED="$TMP_DIR/tagged_all.txt"
: > "$TAGGED"

# 1. Curated verified pool
if [ -f "ip/pool_verified.txt" ]; then
  awk '{
    # ip:port exit_ip ttfb_ms kbps (kbps may be missing or 0 in older formats)
    if (NF >= 2) {
      exit_ip = $2
      ttfb = ($3 != "" ? $3 + 0 : 9999)
      kbps = ($4 != "" ? $4 + 0.0 : 0.0)
      printf "curated\t%s\t%s\t%d\t%.1f\n", $1, exit_ip, ttfb, kbps
    }
  }' ip/pool_verified.txt >> "$TAGGED"
  echo "Loaded ip/pool_verified.txt: $(wc -l < ip/pool_verified.txt | tr -d ' ') rows"
fi

# 2. Freshpoll live pools
find . -type f \( -name "pool_fresh_live.txt" -o -name "pool_fresh_live*.txt" \) 2>/dev/null | while read -r f; do
  awk '{
    if (NF >= 2) {
      exit_ip = $2
      ttfb = ($3 != "" ? $3 + 0 : 9999)
      kbps = ($4 != "" ? $4 + 0.0 : 0.0)
      printf "freshpoll\t%s\t%s\t%d\t%.1f\n", $1, exit_ip, ttfb, kbps
    }
  }' "$f" >> "$TAGGED"
  echo "Loaded $f: $(wc -l < "$f" | tr -d ' ') rows"
done

# 3. Cloud scan pools
find . -type f \( -name "pool_cloud.txt" -o -name "pool_cloud_*.txt" \) 2>/dev/null | while read -r f; do
  awk '{
    if (NF >= 2) {
      exit_ip = $2
      ttfb = ($3 != "" ? $3 + 0 : 9999)
      kbps = ($4 != "" ? $4 + 0.0 : 0.0)
      printf "cloud_scan\t%s\t%s\t%d\t%.1f\n", $1, exit_ip, ttfb, kbps
    }
  }' "$f" >> "$TAGGED"
  echo "Loaded $f: $(wc -l < "$f" | tr -d ' ') rows"
done

TOTAL_TAGGED=$(wc -l < "$TAGGED" | tr -d ' ')
echo "Total raw records collected across all pools: $TOTAL_TAGGED"

# Deduplicate by exit IP (field 3), preferring FAST over SLOW, lowest TTFB, highest kbps
# Output master_pool.txt: ip:port exit_ip ttfb_ms kbps
awk -F'\t' '
{
  orig = $1
  proxy = $2
  exit_ip = $3
  ttfb = $4 + 0
  kbps = $5 + 0.0

  is_fast = (ttfb < 1000 && kbps >= 300.0)

  # Track origin presence for summary
  origins[exit_ip, orig] = 1

  if (!(exit_ip in seen)) {
    seen[exit_ip] = 1
    best_proxy[exit_ip] = proxy
    best_ttfb[exit_ip] = ttfb
    best_kbps[exit_ip] = kbps
    best_fast[exit_ip] = is_fast
  } else {
    # If currently not fast, but new one is fast, replace
    if (!best_fast[exit_ip] && is_fast) {
      best_proxy[exit_ip] = proxy
      best_ttfb[exit_ip] = ttfb
      best_kbps[exit_ip] = kbps
      best_fast[exit_ip] = 1
    } else if (best_fast[exit_ip] == is_fast) {
      # Both fast or both slow: pick lowest ttfb, or higher kbps
      if (ttfb < best_ttfb[exit_ip] || (ttfb == best_ttfb[exit_ip] && kbps > best_kbps[exit_ip])) {
        best_proxy[exit_ip] = proxy
        best_ttfb[exit_ip] = ttfb
        best_kbps[exit_ip] = kbps
      }
    }
  }
}
END {
  for (eip in seen) {
    p = best_proxy[eip]
    t = best_ttfb[eip]
    k = best_kbps[eip]
    f = best_fast[eip]

    printf "%s %s %d %.1f\n", p, eip, t, k > "master_pool.txt"
    if (f) {
      printf "%s %s %d %.1f\n", p, eip, t, k > "master_fast.txt"
      fast_count++
    } else {
      slow_count++
    }
    total_unique++

    # Count origins
    c = origins[eip, "curated"] + 0
    fp = origins[eip, "freshpoll"] + 0
    cs = origins[eip, "cloud_scan"] + 0

    if (c) orig_c++
    if (fp) orig_fp++
    if (cs) orig_cs++

    if (c && !fp && !cs) only_c++
    if (!c && fp && !cs) only_fp++
    if (!c && !fp && cs) only_cs++
    if (c + fp + cs > 1) overlap++
  }

  print "=== MASTER MERGE SUMMARY ===" > "master_summary.txt"
  printf "generated_at: %s\n", strftime("%Y-%m-%d %H:%M:%SZ", systime(), 1) > "master_summary.txt"
  printf "total_input_lines: %d\n", NR > "master_summary.txt"
  printf "total_unique_exits: %d\n", total_unique > "master_summary.txt"
  printf "tier_FAST: %d (%.2f%%)\n", fast_count, (total_unique > 0 ? 100.0 * fast_count / total_unique : 0) > "master_summary.txt"
  printf "tier_SLOW: %d (%.2f%%)\n", slow_count, (total_unique > 0 ? 100.0 * slow_count / total_unique : 0) > "master_summary.txt"
  print "\n--- By Origin (Unique Exit IPs) ---" > "master_summary.txt"
  printf "curated_pool_verified: %d\n", orig_c > "master_summary.txt"
  printf "freshpoll_sources:     %d\n", orig_fp > "master_summary.txt"
  printf "cloud_scan:            %d\n", orig_cs > "master_summary.txt"
  print "\n--- Exclusive vs Overlap ---" > "master_summary.txt"
  printf "exclusive_to_curated:   %d\n", only_c > "master_summary.txt"
  printf "exclusive_to_freshpoll: %d\n", only_fp > "master_summary.txt"
  printf "exclusive_to_cloud:     %d\n", only_cs > "master_summary.txt"
  printf "multi_source_overlap:   %d\n", overlap > "master_summary.txt"
}
' "$TAGGED"

# Sort outputs cleanly by TTFB
sort -k3,3n -k4,4nr master_pool.txt -o master_pool.txt
if [ -f master_fast.txt ]; then
  sort -k3,3n -k4,4nr master_fast.txt -o master_fast.txt
else
  touch master_fast.txt
fi

cat master_summary.txt
echo "master_pool.txt: $(wc -l < master_pool.txt | tr -d ' ') unique exits"
echo "master_fast.txt: $(wc -l < master_fast.txt | tr -d ' ') FAST exits"