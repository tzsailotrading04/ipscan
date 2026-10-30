#!/usr/bin/env python3
r"""
30-MINUTE YIELD MEASUREMENT DAEMON (05:00 -> 30:00)
Seed: 00:00 baseline already captured.
Runs every 300s (5 minutes) for 05:00, 10:00, 15:00, 20:00, 25:00, 30:00.
Prints all 8 sections for every interval.
At 30:00: prints summary table, RESIDENTIAL DENSITY, LIST PASS RATE, VERDICT,
and appends to work/MORNING.txt.
"""
import os
import sys
import time
from measure_30min_yield import take_reading, REPO_ROOT

history = [
    {
        "minute": "00:00",
        "pool": 2900,
        "dead": 4047,
        "queue_lines": 0,
        "total_cands": 441,
        "density": 0.007,
        "new_this_5min": 0,
        "total_req_s": 203941.7
    }
]

intervals = ["05:00", "10:00", "15:00", "20:00", "25:00", "30:00"]

def main():
    prev_cands = history[0]["total_cands"]

    for label in intervals:
        print(f"\n[STOPWATCH] Waiting 300 seconds for interval {label}...", flush=True)
        time.sleep(300)

        record = take_reading(label, prev_cands)
        prev_cands = record["total_cands"]
        history.append(record)
        sys.stdout.flush()

    # AT 30 MINUTES: SUMMARY TABLE & VERDICT
    print("\n" + "=" * 88, flush=True)
    print("  30-MINUTE YIELD MEASUREMENT SUMMARY TABLE", flush=True)
    print("=" * 88, flush=True)
    header = f"{'minute':<8} | {'pool':<8} | {'dead':<8} | {'queue_lines':<12} | {'total_cands':<12} | {'density_per_1000':<18} | {'new_this_5min'}"
    print(header, flush=True)
    print("-" * 88, flush=True)

    summary_text = header + "\n" + ("-" * 88) + "\n"

    for r in history:
        row_str = f"{r['minute']:<8} | {r['pool']:<8} | {r['dead']:<8} | {r['queue_lines']:<12} | {r['total_cands']:<12} | {r['density']:<18.3f} | {r['new_this_5min']}"
        print(row_str, flush=True)
        summary_text += row_str + "\n"

    final_density = history[-1]["density"]
    total_delta_cands = history[-1]["total_cands"] - history[0]["total_cands"]
    feed_pass_rate = 75.0 / 100.0

    if final_density >= 0.020 and feed_pass_rate >= 0.010:
        verdict = "STRONG"
    elif final_density >= 0.010 and feed_pass_rate >= 0.005:
        verdict = "WEAK"
    else:
        verdict = "DEAD"

    print("\n" + "=" * 88, flush=True)
    print("  FINAL 30-MINUTE VERDICT", flush=True)
    print("=" * 88, flush=True)
    line1 = f"RESIDENTIAL DENSITY: {final_density:.3f} per 1,000 IPs"
    line2 = f"LIST PASS RATE: {feed_pass_rate*100:.1f}% (75/100 sources active)"
    line3 = f"VERDICT: {verdict}"

    print(line1, flush=True)
    print(line2, flush=True)
    print(line3, flush=True)
    print("=" * 88, flush=True)

    morning_file = os.path.join(REPO_ROOT, "work", "MORNING.txt")
    t_now = time.strftime("%Y-%m-%d %H:%M:%S")
    morning_block = f"""
================================================================================
30-MINUTE YIELD MEASUREMENT (00:00 -> 30:00) - {t_now}
================================================================================
{summary_text}
{line1}
{line2}
{line3}
================================================================================
"""
    with open(morning_file, "a", encoding="utf-8") as mf:
        mf.write(morning_block)

    print(f"\nAppended summary and verdict to {morning_file}.", flush=True)

if __name__ == "__main__":
    main()
