from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple
import hashlib
import subprocess
import re


def _normalize_remote_repo_input(raw: str) -> Tuple[str, Optional[str]]:
    cleaned = raw.replace("\\", "/").strip()
    cleaned = cleaned.replace("https:/", "https://").replace("http:/", "http://")
    branch_in_url = None
    if cleaned.startswith("git@"):
        return cleaned, branch_in_url
    if "://" not in cleaned and cleaned.startswith("github.com"):
        cleaned = f"https://{cleaned}"
    if cleaned.startswith("http") and "/tree/" in cleaned:
        base, remainder = cleaned.split("/tree/", 1)
        branch_in_url = remainder.split("/", 1)[0]
        cleaned = base
    if cleaned.endswith("/"):
        cleaned = cleaned[:-1]
    if cleaned.startswith("http") and not cleaned.endswith(".git"):
        cleaned = f"{cleaned}.git"
    return cleaned, branch_in_url


def resolve_framework_root(explicit: Optional[str] = None) -> Path:
    """Resolve the framework repository root path.

    Extended behavior: if an explicit value resembles a remote git URL, clone (once) into ./framework_repos/<hash>.
    Order:
      1) Explicit local path or remote URL (auto-clone)
      2) ENV FRAMEWORK_REPO_ROOT if exists
      3) First directory under ./framework_repos
    """
    # Allow override to keep consistency across all endpoints
    clone_base_env = os.getenv("FRAMEWORK_CLONE_BASE", "framework_repos")
    default_root = Path(clone_base_env).expanduser().resolve()
    default_root.mkdir(parents=True, exist_ok=True)

    # 1) Explicit handling
    def _extract_embedded_remote(raw: str) -> Optional[str]:
        """Extract a remote git URL if the user accidentally prefixed it with a local path.
        Example: C:\workspace\git@github.com:org/repo.git -> git@github.com:org/repo.git
        """
        markers = ["git@github.com:", "https://github.com/", "http://github.com/"]
        for marker in markers:
            idx = raw.find(marker)
            if idx != -1:
                return raw[idx:].replace("\\", "/").strip()
        return None

    if explicit:
        raw = explicit.strip()
        # Detect embedded remote even if user passed a combined local+remote path
        embedded = _extract_embedded_remote(raw)
        if embedded:
            raw = embedded
        is_remote = bool(re.match(r"^(git@|https?://).*", raw)) or ("github.com" in raw and (raw.startswith("git@") or "https://" in raw or "http://" in raw))
        if is_remote:
            clone_url, branch_in_url = _normalize_remote_repo_input(raw)
            # Canonicalize clone_url to reduce duplicate hashes
            base_canonical = clone_url.rstrip('/')
            if base_canonical.endswith('.git.git'):
                base_canonical = base_canonical[:-4]
            # Remove /tree/<branch> from hash source if present (already extracted)
            base_canonical = re.sub(r'/tree/[^/]+$', '', base_canonical)
            slug_source = base_canonical + (f"#{branch_in_url}" if branch_in_url else "")
            local_slug = hashlib.sha1(slug_source.encode("utf-8")).hexdigest()[:12]
            target_dir = (default_root / local_slug).resolve()
            if not target_dir.exists():
                target_dir.parent.mkdir(parents=True, exist_ok=True)
                try:
                    subprocess.run(["git", "clone", clone_url, str(target_dir)], check=True)
                except (subprocess.CalledProcessError, FileNotFoundError) as exc:
                    raise FileNotFoundError(f"Git clone failed for '{clone_url}': {exc}") from exc
            if branch_in_url:
                try:
                    subprocess.run(["git", "-C", str(target_dir), "checkout", branch_in_url], check=True)
                except (subprocess.CalledProcessError, FileNotFoundError) as exc:
                    raise FileNotFoundError(f"Git checkout failed for branch '{branch_in_url}': {exc}") from exc
            return target_dir
        else:
            local_path = Path(raw).expanduser().resolve()
            if local_path.exists() and local_path.is_dir():
                return local_path
            # Fall through to other strategies if explicit path not found

    # 2) Environment variable
    env_root = os.getenv("FRAMEWORK_REPO_ROOT")
    if env_root:
        env_path = Path(env_root).expanduser().resolve()
        if env_path.exists() and env_path.is_dir():
            return env_path

    # 3) First directory under framework_repos
    subdirs = [p for p in default_root.iterdir() if p.is_dir()]
    subdirs.sort(key=lambda p: p.name)
    if subdirs:
        return subdirs[0]

    raise FileNotFoundError(
        "Framework repository root not found. Provide a local path, remote git URL, set FRAMEWORK_REPO_ROOT, or clone into ./framework_repos."
    )
