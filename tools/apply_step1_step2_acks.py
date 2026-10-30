#!/usr/bin/env python3
import os
import glob
import re

REPO_ROOT = r"D:\DEpinFarm"
MASTER = os.path.join(REPO_ROOT, "kaggle", "cl_shodan", "run.py")

with open(MASTER, "r", encoding="utf-8") as f:
    text = f.read()

# 1. Update queue_dir to also define acks_dir
old_setup = """    queue_dir = os.path.join(REPO, "ip", "harvest", "queue")
    os.makedirs(queue_dir, exist_ok=True)"""

new_setup = """    queue_dir = os.path.join(REPO, "ip", "harvest", "queue")
    acks_dir = os.path.join(REPO, "ip", "harvest", "acks")
    os.makedirs(queue_dir, exist_ok=True)
    os.makedirs(acks_dir, exist_ok=True)"""

if old_setup in text:
    text = text.replace(old_setup, new_setup, 1)
else:
    print("Warning: old_setup already updated or not found")

# 2. In get_candidate_batch:
old_gcb = """                qf_path = os.path.join(queue_dir, qf_name)
                ack_marker = qf_path + f".ack_{shard_idx}\""""

new_gcb = """                qf_path = os.path.join(queue_dir, qf_name)
                ack_marker = os.path.join(acks_dir, f"{qf_name}.ack_{shard_idx}")"""

if old_gcb in text:
    text = text.replace(old_gcb, new_gcb, 1)
else:
    print("Warning: old_gcb already updated or not found")

# Check os.remove(os.path.join(acks_dir, a))
old_gcb_del = """                    all_acks = [f for f in os.listdir(queue_dir) if f.startswith(qf_name + ".ack_")]
                    if len(all_acks) >= NUM_SHARDS:
                        try:
                            os.remove(qf_path)
                            for a in all_acks:
                                os.remove(os.path.join(queue_dir, a))"""

new_gcb_del = """                    all_acks = [f for f in os.listdir(acks_dir) if f.startswith(qf_name + ".ack_")]
                    if len(all_acks) >= NUM_SHARDS:
                        try:
                            os.remove(qf_path)
                            for a in all_acks:
                                os.remove(os.path.join(acks_dir, a))"""

if old_gcb_del in text:
    text = text.replace(old_gcb_del, new_gcb_del, 1)

# 3. In consume_queue_stage:
old_cqs = """            qf_path = os.path.join(queue_dir, qf_name)
            ack_file = os.path.join(queue_dir, f"{qf_name}.ack_{shard_idx}\""""

new_cqs = """            qf_path = os.path.join(queue_dir, qf_name)
            ack_file = os.path.join(acks_dir, f"{qf_name}.ack_{shard_idx}")"""

if old_cqs in text:
    text = text.replace(old_cqs, new_cqs, 1)
else:
    print("Warning: old_cqs already updated or not found")

old_cqs_del = """            acks = [f for f in os.listdir(queue_dir) if f.startswith(f"{qf_name}.ack_") and not f.endswith(".tmp")]
            if len(acks) >= NUM_SHARDS:
                try:
                    os.remove(qf_path)
                    for a in acks:
                        os.remove(os.path.join(queue_dir, a))"""

new_cqs_del = """            acks = [f for f in os.listdir(acks_dir) if f.startswith(f"{qf_name}.ack_") and not f.endswith(".tmp")]
            if len(acks) >= NUM_SHARDS:
                try:
                    os.remove(qf_path)
                    for a in acks:
                        os.remove(os.path.join(acks_dir, a))"""

if old_cqs_del in text:
    text = text.replace(old_cqs_del, new_cqs_del, 1)

# Update ENGINE_VER to v98.185
text = re.sub(r'ENGINE_VER = "[^"]+"', 'ENGINE_VER = "v98.185"', text)

with open(MASTER, "w", encoding="utf-8") as f:
    f.write(text)

print("Master kaggle/cl_shodan/run.py updated successfully.")

# Propagate to all 34 shards
# For each shard, we replace SHARD_TAG = "XX" and shard_idx = XX
for s in range(34):
    stag = f"{s:02d}"
    shard_run = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{stag}", "run.py")
    shard_content = text
    shard_content = re.sub(r'SHARD_TAG = "[^"]+"', f'SHARD_TAG = "{stag}"', shard_content)
    shard_content = re.sub(r'shard_idx = \d+', f'shard_idx = {s}', shard_content)
    with open(shard_run, "w", encoding="utf-8") as sf:
        sf.write(shard_content)

print("Propagated to all 34 shards (00..33).")
