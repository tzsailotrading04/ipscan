import os

def fast_size(path):
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False) and not entry.is_symlink():
                        total += fast_size(entry.path)
                except (PermissionError, FileNotFoundError, OSError):
                    pass
    except (PermissionError, FileNotFoundError, OSError):
        pass
    return total

check_list = [
    r"C:\hiberfil.sys",
    r"C:\swapfile.sys",
    r"C:\Users\pc\.gemini",
    r"C:\Users\pc\AppData\Local\Temp",
    r"C:\Users\pc\AppData\Local\pip",
    r"C:\Users\pc\AppData\Local\Google",
    r"C:\Users\pc\AppData\Local\Microsoft",
    r"C:\Users\pc\AppData\Local\Programs",
    r"C:\Users\pc\AppData\Roaming",
    r"C:\Users\pc\.vscode",
    r"C:\Users\pc\Downloads",
    r"C:\Users\pc\Desktop",
    r"C:\Windows\Temp",
    r"C:\Windows\SoftwareDistribution\Download",
    r"C:\Windows\System32",
    r"C:\Windows\WinSxS",
]

print("=" * 65, flush=True)
print(f"{'Path':<45} : {'Size (GB)':>10}", flush=True)
print("=" * 65, flush=True)
for p in check_list:
    if os.path.exists(p):
        if os.path.isfile(p):
            sz = os.path.getsize(p) / (1024**3)
        else:
            sz = fast_size(p) / (1024**3)
        print(f"{p:<45} : {sz:>9.2f} GB", flush=True)
