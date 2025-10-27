# executor.py
import subprocess
import tempfile
import os

def run_trial(script_content: str):
    """Write script to temp file and run playwright test."""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".spec.ts") as tmp:
            tmp.write(script_content.encode("utf-8"))
            tmp_path = tmp.name

        cmd = ["npx", "playwright", "test", tmp_path, "--reporter=line"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",  # avoid Windows codepage decode failures
        )

        success = result.returncode == 0
        logs = result.stdout + "\n" + result.stderr

        os.unlink(tmp_path)  # cleanup
        return success, logs
    except Exception as e:
        return False, str(e)
