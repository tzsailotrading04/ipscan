#!/usr/bin/env bash
set -uo pipefail
[ -s ip/public_pool.txt ] || exit 0
curl -fsSL --max-time 120 "https://www.peeringdb.com/api/net" -o /tmp/pdb.json || exit 0
curl -fsSL --max-time 120 "https://iptoasn.com/data/ip2asn-v4-u32.tsv.gz" -o /tmp/ip2asn.gz || exit 0
gunzip -c /tmp/ip2asn.gz > /tmp/ip2asn.tsv
python3 - <<'PY'
import json, ipaddress, bisect
pdb = json.load(open('/tmp/pdb.json'))['data']
res = {str(n['asn']) for n in pdb if n.get('info_type') == 'Cable/DSL/ISP'}
rng = []
for line in open('/tmp/ip2asn.tsv'):
    p = line.rstrip('\n').split('\t')
    if len(p) >= 3:
        try: rng.append((int(p[0]), int(p[1]), p[2]))
        except: pass
rng.sort()
starts = [r[0] for r in rng]
def asn_of(ip):
    i = int(ipaddress.ip_address(ip))
    k = bisect.bisect_right(starts, i) - 1
    return rng[k][2] if k >= 0 and rng[k][1] >= i else ''
R, D = [], []
for line in open('ip/public_pool.txt'):
    line = line.rstrip('\n')
    if not line: continue
    ip = line.split('\t')[0].split(':')[0]
    (R if asn_of(ip) in res else D).append(line)
open('ip/public_residential.txt','w').write(('\n'.join(R)+'\n') if R else '')
open('ip/public_dc.txt','w').write(('\n'.join(D)+'\n') if D else '')
print('residential', len(R), 'dc', len(D))
PY
