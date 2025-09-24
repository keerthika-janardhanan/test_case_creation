import argparse
import subprocess
import os
import sys

def record_flow(flow_name: str, url: str):
    os.makedirs("./recordings", exist_ok=True)
    trace_file = f"./recordings/{flow_name}.zip"

    # Construct Playwright codegen command
    cmd = f"npx playwright codegen {url} --save-trace={trace_file}"

    # On Windows, use shell + new console
    creationflags = subprocess.CREATE_NEW_CONSOLE if sys.platform.startswith("win") else 0

    subprocess.run(cmd, shell=True, creationflags=creationflags)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--flow_name", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--user", required=True)  # not used yet, but kept for metadata
    args = parser.parse_args()

    record_flow(args.flow_name, args.url)
