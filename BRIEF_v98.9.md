# BRIEF v98.9 — AdaptivePacer + STOP_FLAG

## Problem being fixed
Fleet was stuck at 99.997% HTTP 429 (rate_limit=105,597 of 105,600).
Root cause: LightPacer used a 1-second window counter, so it fired a
~180-request burst at every 1s boundary, then idled. Cloudflare saw the
burst, not the average rate. Fix = smooth per-request spacing + AIMD.
Second problem: Kaggle API cannot cancel a running session (403), so we
need an in-repo kill switch the kernel polls itself.

## Job 1 — Replace LightPacer with AdaptivePacer
- aiohttp session, keepalive, one shared connection pool
- Smooth spacing: a single global slot generator. Each request computes
  its own send time = next_slot, increments next_slot by interval, then
  sleeps to that time. No window bursts.
- AIMD: start 50 req/s, floor 6, ceiling 90
    * HTTP 200  -> rate += 0.5 (additive increase), cap at ceiling
    * HTTP 429  -> rate *= 0.5 (multiplicative decrease), floor at lo
    * Honour Retry-After header: global pause min(retry_after, 300)s
- Never raise rate above ceiling; never below floor.

## Job 2 — STOP_FLAG kill switch
- Flag file: work/STOP_SHODAN
- Global STOPPING=False
- Monitor coroutine every 60s: git fetch origin main + git reset --hard
  origin/main (marker-tolerant), then check for work/STOP_SHODAN. If
  present -> STOPPING=True.
- Workers check STOPPING at top of each loop; on True they finish the
  in-flight request, flush progress atomically (tmp + os.replace), exit 0.

## Preserved from earlier versions
- Strided sharding: ordered[SHARD_IDX::NUM_SHARDS]
- Atomic progress writes (tmp + os.replace)
- read_offset() takes max integer found (tolerates conflict markers)
- Startup purge of stale shard files
- git fetch + git reset --hard (never rebase in a kernel)
