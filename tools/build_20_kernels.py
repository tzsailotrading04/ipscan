import os
import json

ROOT = r"D:\DEpinFarm"
TEMPLATE_PATH = os.path.join(ROOT, "tools", "farm_kernel_template.py")

NOTEBOOK_ASSIGNMENTS = [
    # acct1 (lalthazualasailo)
    ("acct1", "lalthazualasailo", "a", 0),
    ("acct1", "lalthazualasailo", "b", 1),
    ("acct1", "lalthazualasailo", "g", 6),
    ("acct1", "lalthazualasailo", "h", 7),
    ("acct1", "lalthazualasailo", "i", 8),

    # acct2 (zomuanpuia)
    ("acct2", "zomuanpuia", "c", 2),
    ("acct2", "zomuanpuia", "d", 3),
    ("acct2", "zomuanpuia", "j", 9),
    ("acct2", "zomuanpuia", "k", 10),
    ("acct2", "zomuanpuia", "l", 11),

    # acct3 (laldinthari)
    ("acct3", "laldinthari", "e", 4),
    ("acct3", "laldinthari", "f", 5),
    ("acct3", "laldinthari", "m", 12),
    ("acct3", "laldinthari", "n", 13),
    ("acct3", "laldinthari", "o", 14),

    # acct4 (lalsangkima)
    ("acct4", "lalsangkima", "p", 15),
    ("acct4", "lalsangkima", "q", 16),
    ("acct4", "lalsangkima", "r", 17),
    ("acct4", "lalsangkima", "s", 18),
    ("acct4", "lalsangkima", "t", 19),

    # acct6 (spectatorlone)
    ("acct6", "spectatorlone", "u", 20),
    ("acct6", "spectatorlone", "v", 21),
    ("acct6", "spectatorlone", "w", 22),
    ("acct6", "spectatorlone", "x", 23),
    ("acct6", "spectatorlone", "y", 24),

    # acct5 (remruata)
    ("acct5", "remruata", "z", 25),
    ("acct5", "remruata", "aa", 26),
]

def main():
    template_code = open(TEMPLATE_PATH, "r", encoding="utf-8").read()

    print(f"Generating {len(NOTEBOOK_ASSIGNMENTS)} kernel directories...", flush=True)
    count = 0

    for acct, user, letter, slice_idx in NOTEBOOK_ASSIGNMENTS:
        folder_name = f"cl_{letter}"
        nb_dir = os.path.join(ROOT, "kaggle", folder_name)
        os.makedirs(nb_dir, exist_ok=True)

        slug = f"ipscan-cl-{letter}"
        meta = {
            "id": f"{user}/{slug}",
            "title": slug,
            "code_file": "run.py",
            "language": "python",
            "kernel_type": "script",
            "is_private": True,
            "enable_gpu": False,
            "enable_internet": True,
            "dataset_sources": [],
            "competition_sources": [],
            "kernel_sources": []
        }

        # Write metadata
        with open(os.path.join(nb_dir, "kernel-metadata.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(meta, f, indent=2)

        # Write run.py
        k_code = template_code.replace("__SLICE_IDX__", str(slice_idx)).replace("__KERNEL_SLUG__", f"{user}/{slug}")
        with open(os.path.join(nb_dir, "run.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write(k_code)

        # Remove old kernel.py if exists
        old_k = os.path.join(nb_dir, "kernel.py")
        if os.path.exists(old_k):
            try: os.remove(old_k)
            except Exception: pass

        print(f"  [{acct}] {folder_name} -> {user}/{slug} (slice_idx={slice_idx})")
        count += 1

    print(f"\nSLICES_WRITTEN {count}")

if __name__ == "__main__":
    main()
