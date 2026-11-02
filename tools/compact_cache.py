import re, sys
p = re.compile(r'^\d+\.\d+\.\d+\.\d+:\d+$')
src, dst = sys.argv[1], sys.argv[2]
D = {}
with open(src, 'r', errors='ignore') as f:
    for l in f:
        if l.startswith('['):
            f2 = l.split(None, 3)
            if len(f2) > 2 and p.match(f2[2]):
                D[f2[2]] = l.rstrip('\n')
        else:
            f2 = l.split(None, 2)
            if len(f2) > 1 and p.match(f2[1]):
                D[f2[1]] = l.rstrip('\n')
            elif f2 and p.match(f2[0]):
                D[f2[0]] = l.rstrip('\n')
out = sorted(D)
with open(dst, 'w') as f:
    f.write('\n'.join(D[k] for k in out))
print(f"{src}: {len(D)} unique written to {dst}")
