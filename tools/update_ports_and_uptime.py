import os
import re

REPO_ROOT = r"D:\DEpinFarm"

def main():
    for i in range(20):
        s_tag = f"{i:02d}"
        run_path = os.path.join(REPO_ROOT, "kaggle", f"cl_shodan_{s_tag}", "run.py")
        if not os.path.exists(run_path):
            print(f"Error: {run_path} does not exist!")
            continue

        with open(run_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Update DIRECT_PORTS
        # Look for DIRECT_PORTS = [...]
        content = re.sub(
            r'DIRECT_PORTS\s*=\s*\[[^\]]*\]',
            'DIRECT_PORTS = [3128, 8080, 8000, 8118, 8888, 1080]',
            content
        )

        # Update MAX_UPTIME_SECONDS
        content = re.sub(
            r'MAX_UPTIME_SECONDS\s*=\s*\d+.*',
            'MAX_UPTIME_SECONDS = 28800  # 8-hour session cap',
            content
        )

        with open(run_path, "w", encoding="utf-8") as f:
            f.write(content)

    print("Updated all 20 run.py files.")

if __name__ == "__main__":
    main()
