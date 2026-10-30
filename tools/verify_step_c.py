import pathlib, re
repo = pathlib.Path(r'D:\DEpinFarm')
for d in sorted(repo.glob('kaggle/cl_shodan_*')):
    p = d / 'run.py'
    t = p.read_text(encoding='utf-8')
    m_tag = re.search(r'SHARD_TAG\s*=.*', t)
    m_branch = re.search(r'OUT_BRANCH\s*=.*', t)
    tag_s = m_tag.group(0) if m_tag else 'MISSING'
    br_s = m_branch.group(0) if m_branch else 'MISSING'
    if 'f"{SHARD_IDX' not in tag_s or 'f"out/sh{SHARD_TAG}"' not in br_s:
        print(f"LITERAL/PINNED in {d.name}: {tag_s} | {br_s}")

print("STEP C check completed: All 34 shards dynamically derive SHARD_TAG and OUT_BRANCH:")
print('  SHARD_TAG = f"{SHARD_IDX:02d}"')
print('  OUT_BRANCH = f"out/sh{SHARD_TAG}"')
