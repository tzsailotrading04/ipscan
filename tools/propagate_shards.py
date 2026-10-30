import os, py_compile

repo = r'D:\DEpinFarm'
master_file = os.path.join(repo, 'kaggle', 'cl_shodan', 'run.py')
with open(master_file, 'r', encoding='utf-8') as f:
    master_template = f.read()

# Propagate to 34 shards
results = []
compile_errors = []

# Compile check master first
try:
    py_compile.compile(master_file, doraise=True)
    results.append(('cl_shodan (master)', True, True, True))
except Exception as e:
    compile_errors.append((master_file, str(e)))

for i in range(34):
    shard_tag = f'{i:02d}'
    shard_dir = os.path.join(repo, 'kaggle', f'cl_shodan_{shard_tag}')
    os.makedirs(shard_dir, exist_ok=True)
    shard_file = os.path.join(shard_dir, 'run.py')

    shard_code = master_template.replace('SHARD_IDX = 0\n', f'SHARD_IDX = {i}\n')
    with open(shard_file, 'w', encoding='utf-8') as f:
        f.write(shard_code)

    # Check stage and ports in file
    has_stage = 'async def consume_queue_stage():' in shard_code and 'await consume_queue_stage()' in shard_code
    has_ports = 'DIRECT_PORTS = [443, 3128, 8080, 8888, 1080, 8118, 80, 4145]' in shard_code

    # Compile check
    compiled = False
    try:
        py_compile.compile(shard_file, doraise=True)
        compiled = True
    except Exception as e:
        compile_errors.append((shard_file, str(e)))

    results.append((f'cl_shodan_{shard_tag}', has_stage, has_ports, compiled))

print('=' * 75)
print('PART B & C VERIFICATION: 34-ROW TABLE')
print('=' * 75)
print(f'{"File":<22} | {"Queue Stage":<15} | {"8 Ports":<12} | {"Compile":<10}')
print('-' * 75)
for name, stage, ports, comp in results[1:]:  # 34 shards
    st_val = "PRESENT" if stage else "MISSING"
    pt_val = "PRESENT" if ports else "MISSING"
    cp_val = "OK" if comp else "FAIL"
    print(f'{name:<22} | {st_val:<15} | {pt_val:<12} | {cp_val:<10}')

print('=' * 75)
if compile_errors:
    print('COMPILE_FAIL:')
    for f, err in compile_errors:
        print(f'  {f}: {err}')
else:
    print('ALL 35 FILES COMPILED CLEANLY WITH ZERO ERRORS!')
