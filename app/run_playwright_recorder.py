"""Wrapper to launch Playwright codegen with the custom XPath selector engine."""

import argparse
import os
import shutil
import signal
import subprocess
from typing import List


def _resolve_npx() -> str:
    candidates = ["npx"]
    if os.name == "nt":
        candidates = ["npx.cmd", "npx.exe", "npx"]
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
    raise FileNotFoundError(
        "Unable to locate 'npx' on PATH. Ensure Node.js is installed and npx is available."
    )


def _build_command(url: str, extra: List[str] | None) -> List[str]:
    npx_executable = _resolve_npx()
    extra = extra or []
    cmd = [npx_executable, "playwright", "codegen", url]
    cmd.extend(arg for arg in extra if arg)
    return cmd


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Playwright codegen with the custom XPath selector engine preloaded."
    )
    parser.add_argument("--url", required=True, help="URL to open in Playwright codegen")
    parser.add_argument(
        "extra_args",
        nargs=argparse.REMAINDER,
        help="Any additional arguments to forward to `npx playwright codegen`",
    )
    args = parser.parse_args()

    engine_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "xpath-selector-engine.js"))

    env = os.environ.copy()
    require_flag = f"--require={engine_path}"
    existing = env.get("NODE_OPTIONS", "")
    if require_flag not in existing:
        env["NODE_OPTIONS"] = (existing + " " + require_flag).strip()
    else:
        env["NODE_OPTIONS"] = existing.strip()

    cmd = _build_command(args.url, args.extra_args)

    creationflags = 0
    if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(cmd, env=env, creationflags=creationflags)

    def _terminate_child(signum, frame):
        if proc.poll() is None:
            proc.terminate()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _terminate_child)
        except (ValueError, OSError):
            pass
    if hasattr(signal, "SIGBREAK"):
        try:
            signal.signal(signal.SIGBREAK, _terminate_child)
        except (ValueError, OSError):
            pass
    try:
        proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
