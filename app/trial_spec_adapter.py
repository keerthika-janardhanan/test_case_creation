import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple, List

logger = logging.getLogger(__name__)

# Note: do not hardcode any example TestCaseID here. We will infer the case id
# from the spec file when available, or use the first credentials row as a
# neutral fallback.


@dataclass
class TrialCredentials:
    base_url: str
    username: str
    password: str


def _extract_titles_from_source(source: str) -> List[str]:
    """Return unique test titles found in a Playwright spec source."""
    titles: List[str] = []
    pattern = re.compile(r"\b(?:run|test)\(\s*['\"]([^'\"]+)['\"]")
    for m in pattern.finditer(source or ""):
        t = m.group(1).strip()
        if t and t not in titles:
            titles.append(t)
    return titles


def _is_id_like(value: str) -> bool:
    # Heuristic for ID-like tokens: contains underscore or all-caps or starts with 'TC'
    if not value:
        return False
    if "_" in value:
        return True
    if value.upper() == value and any(c.isalpha() for c in value):
        return True
    if value.startswith("TC"):
        return True
    return False


def load_trial_credentials(repo_root: Path, case_id: Optional[str] = None) -> Optional[TrialCredentials]:
    """Load trial credentials from trial_run_config.json instead of testmanager.xlsx"""
    trial_config_path = Path(__file__).resolve().parents[1] / "trial_run_config.json"
    
    if not trial_config_path.exists():
        logger.debug("Trial adapter: trial_run_config.json not found at %s", trial_config_path)
        return None
    
    try:
        with open(trial_config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as exc:
        logger.warning("Trial adapter: failed to read trial_run_config.json (%s)", exc)
        return None
    
    base_url = config.get("base_url", "").strip()
    username = config.get("username", "").strip()
    password = config.get("password", "").strip()
    
    if not (username and password):
        logger.warning("Trial adapter: trial_run_config.json missing username or password")
        return None
    
    msg = (
        f"[TrialAdapter] Loaded credentials from trial_run_config.json:\n"
        f"  base_url: {base_url}\n"
        f"  username: {username}\n"
        f"  password: {'*' * len(password)}"
    )
    print(msg)
    logger.info(msg)
    return TrialCredentials(base_url=base_url, username=username, password=password)


def trial_env_overrides(repo_root: Path, case_id: Optional[str] = None, spec_path: Optional[Path] = None) -> Dict[str, str]:
    """
    Build environment variable overrides for trial executions using credentials from trial_run_config.json.
    This enables specs that rely on process.env to use consistent values without editing source files.
    """
    # Always read from trial_run_config.json at the project root
    trial_config_path = Path(__file__).resolve().parents[1] / "trial_run_config.json"
    
    if not trial_config_path.exists():
        logger.warning("Trial adapter: trial_run_config.json not found at %s", trial_config_path)
        return {}
    
    try:
        with open(trial_config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as exc:
        logger.warning("Trial adapter: failed to read trial_run_config.json (%s)", exc)
        return {}
    
    base_url = config.get("base_url", "").strip()
    username = config.get("username", "").strip()
    password = config.get("password", "").strip()
    
    if not (username and password):
        logger.warning("Trial adapter: trial_run_config.json missing username or password")
        return {}
    
    overrides: Dict[str, str] = {}
    # Always override a broad set of common env names so trial ignores .env creds
    if username:
        overrides["USERID"] = username
        overrides["USERNAME"] = username  # alias for tests using USERNAME
        overrides["TRIAL_USER"] = username
        overrides["TRIAL_USERNAME"] = username
        overrides["EMAIL"] = username  # some tests may treat username as email
    if password:
        overrides["PASSWORD"] = password
        overrides["TRIAL_PASSWORD"] = password
    if base_url:
        overrides["BASE_URL"] = base_url
        overrides["URL"] = base_url  # alias for tests using URL
        overrides["TRIAL_BASE_URL"] = base_url
        overrides["TRIAL_URL"] = base_url
    
    logger.info("Trial adapter: loaded credentials from trial_run_config.json (username=%s, base_url=%s)", username, base_url)
    return overrides


def _replace_fill_call(source: str, pattern: str, replacement_value: str) -> Tuple[str, bool]:
    import re

    replaced = False

    def _replacer(match: "re.Match[str]") -> str:
        nonlocal replaced
        replaced = True
        prefix = match.group(1)
        suffix = match.group(2)
        original_value = match.group(0)
        new_value_json = json.dumps(replacement_value)
        result = f"{prefix}{new_value_json}{suffix}"
        
        # Add a 10-second wait after fill to see the value
        result_with_wait = result + "\n      await page.waitForTimeout(10000); // Wait 10s to see filled value"
        
        # Log the replacement for debugging (both print and logger)
        msg = (
            f"[TrialAdapter] Replacing fill call:\n"
            f"  Original: {original_value.strip()}\n"
            f"  Pattern: {pattern}\n"
            f"  Replacement value: {replacement_value}\n"
            f"  JSON-encoded: {new_value_json}\n"
            f"  Result: {result.strip()}\n"
            f"  Added 10s wait after fill"
        )
        print(msg)
        logger.info(msg)
        
        return result_with_wait

    updated = re.sub(pattern, _replacer, source, count=1)
    return updated, replaced


def _adjust_mfa_sequence(source: str) -> Tuple[str, bool]:
    import re

    changed = False

    replacements = [
        (
            r"(\s*)await\s+flow\.enterPasscode\.click\(\);\s*\n",
            "Trial adapter: user handles the MFA prompt manually during trial runs.",
        ),
        (
            r"(\s*)await\s+flow\.enterPasscode\.fill\([^;]*\);\s*\n",
            "Trial adapter: user enters the MFA passcode manually during trial runs.",
        ),
        (
            r"(\s*)await\s+flow\.verify\.click\(\);\s*\n",
            "Trial adapter: user submits verification manually during trial runs.",
        ),
    ]

    updated = source
    for pattern, message in replacements:
        def _replacer(match: "re.Match[str]") -> str:
            nonlocal changed
            changed = True
            indent = match.group(1)
            return f"{indent}// {message}\n"

        updated = re.sub(pattern, _replacer, updated, count=1)

    return updated, changed


def _inject_sign_in_pause(source: str) -> Tuple[str, bool]:
    import re

    if "page.waitForTimeout(90000)" in source:
        return source, False

    pattern = r"(await\s+flow\.signIn\.click\(\);\s*\n)"
    injected = False

    def _replacer(match: "re.Match[str]") -> str:
        nonlocal injected
        injected = True
        return (
            f"{match.group(1)}      // Trial adapter: wait 90s to allow manual MFA passcode entry\n"
            "      await page.waitForTimeout(90000);\n"
        )

    updated = re.sub(pattern, _replacer, source, count=1)
    return updated, injected


def _ensure_navigation(source: str, base_url: str) -> Tuple[str, bool]:
    if "page.goto(" in source:
        return source, False
    marker = "    flow = new PageObject(page);"
    if marker not in source:
        return source, False
    navigation_line = f"    await page.goto({json.dumps(base_url)}, {{ waitUntil: 'load' }});"
    updated = source.replace(marker, f"{marker}\n{navigation_line}", 1)
    return updated, True


def _add_login_page_wait(source: str) -> Tuple[str, bool]:
    """Add a 20-second wait after navigation to login page to see what values are being filled."""
    import re
    
    # Add wait after page.goto
    if "page.goto(" in source and "await page.waitForTimeout(20000); // Wait to see login page" not in source:
        pattern = r"(await\s+page\.goto\([^;]+;\s*\n)"
        
        def _replacer(match: "re.Match[str]") -> str:
            return f"{match.group(1)}    await page.waitForTimeout(20000); // Wait 20s to see login page and filled values\n"
        
        updated = re.sub(pattern, _replacer, source, count=1)
        if updated != source:
            logger.info("[TrialAdapter] Added 20s wait after page.goto to inspect login page")
            print("[TrialAdapter] Added 20s wait after page.goto to inspect login page")
            return updated, True
    
    return source, False


def adapt_spec_content_for_trial(source: str, repo_root: Path) -> Tuple[str, bool]:
    """Return transformed spec content for trial run; bool indicates change."""
    logger.info("[TrialAdapter] ===== Starting spec adaptation for trial run =====")
    print("\n[TrialAdapter] ===== Starting spec adaptation for trial run =====")
    credentials = load_trial_credentials(repo_root)
    if not credentials:
        logger.info("[TrialAdapter] No credentials found, skipping adaptation")
        print("[TrialAdapter] No credentials found, skipping adaptation")
        return source, False

    updated = source
    changed_any = False

    # More flexible patterns that match any locator name with .fill()
    # Pattern 1: Try specific flow.userName / flow.password first
    logger.info("[TrialAdapter] Attempting to replace username fill call (flow.userName)...")
    print("\n[TrialAdapter] Attempting to replace username fill call (flow.userName)...")
    updated, user_changed = _replace_fill_call(
        updated,
        r"(await\s+flow\.userName\.fill\()\s*(?:['\"].*?['\"])(\);)",
        credentials.username,
    )
    logger.info(f"[TrialAdapter] Username replaced: {user_changed}")
    print(f"[TrialAdapter] Username replaced: {user_changed}")
    
    logger.info("[TrialAdapter] Attempting to replace password fill call (flow.password)...")
    print("\n[TrialAdapter] Attempting to replace password fill call (flow.password)...")
    updated, pass_changed = _replace_fill_call(
        updated,
        r"(await\s+flow\.password\.fill\()\s*(?:['\"].*?['\"])(\);)",
        credentials.password,
    )
    logger.info(f"[TrialAdapter] Password replaced: {pass_changed}")
    print(f"[TrialAdapter] Password replaced: {pass_changed}")

    # Pattern 2: If not found, try generic patterns for username-like and password-like fields
    if not user_changed:
        logger.info("[TrialAdapter] Trying generic username patterns (user|username|userid|email)...")
        print("\n[TrialAdapter] Trying generic username patterns...")
        # Match any .fill() where the locator name contains user/username/userid/email
        updated, user_changed = _replace_fill_call(
            updated,
            r"(await\s+(?:flow|page|locators)\.(?:user|username|userName|userid|userId|email)[^.]*\.fill\()\s*(?:['\"].*?['\"])(\);)",
            credentials.username,
        )
        logger.info(f"[TrialAdapter] Generic username replaced: {user_changed}")
        print(f"[TrialAdapter] Generic username replaced: {user_changed}")
    
    if not pass_changed:
        logger.info("[TrialAdapter] Trying generic password patterns (password|pwd|pass)...")
        print("\n[TrialAdapter] Trying generic password patterns...")
        updated, pass_changed = _replace_fill_call(
            updated,
            r"(await\s+(?:flow|page|locators)\.(?:password|pwd|pass)[^.]*\.fill\()\s*(?:['\"].*?['\"])(\);)",
            credentials.password,
        )
        logger.info(f"[TrialAdapter] Generic password replaced: {pass_changed}")
        print(f"[TrialAdapter] Generic password replaced: {pass_changed}")

    # Pattern 3: If still not found, try to find ANY .fill() calls and log them
    if not (user_changed or pass_changed):
        logger.warning("[TrialAdapter] No username/password fields found with standard patterns!")
        print("\n[TrialAdapter] WARNING: No username/password fields found!")
        print("[TrialAdapter] Searching for all .fill() calls in the script...")
        
        import re
        # More comprehensive pattern to match various fill call formats
        fill_patterns = [
            r"await\s+([^\s]+)\.fill\([^)]*\);",  # await locator.fill()
            r"await\s+page\.locator\([^)]+\)\.fill\([^)]*\);",  # await page.locator().fill()
            r"await\s+page\.getBy[A-Z][a-z]+\([^)]+\)\.fill\([^)]*\);",  # await page.getByRole().fill()
        ]
        
        all_fills = []
        for pattern in fill_patterns:
            fills = re.findall(pattern, source, re.IGNORECASE)
            all_fills.extend(fills)
        
        if all_fills:
            logger.info(f"[TrialAdapter] Found {len(all_fills)} .fill() calls:")
            print(f"[TrialAdapter] Found {len(all_fills)} .fill() calls:")
            for i, locator in enumerate(set(all_fills)[:10], 1):  # Show first 10 unique
                logger.info(f"  {i}. {locator}.fill()")
                print(f"  {i}. {locator}.fill()")
        else:
            # No .fill() calls found - show sample of the script to debug
            logger.info("[TrialAdapter] No .fill() calls found in script")
            print("[TrialAdapter] No .fill() calls found in script")
            print("\n[TrialAdapter] Showing first 30 lines of script for debugging:")
            lines = source.split('\n')[:30]
            for i, line in enumerate(lines, 1):
                print(f"  {i}: {line}")
        
        # Return without changes since we couldn't find login fields
        return source, False

    if not (user_changed or pass_changed):
        # No login steps detected; nothing to adapt.
        return source, False

    changed_any |= user_changed or pass_changed

    updated, nav_changed = _ensure_navigation(updated, credentials.base_url)
    changed_any |= nav_changed

    updated, wait_changed = _add_login_page_wait(updated)
    changed_any |= wait_changed

    updated, pause_changed = _inject_sign_in_pause(updated)
    changed_any |= pause_changed

    updated, strip_changed = _adjust_mfa_sequence(updated)
    changed_any |= strip_changed

    summary = (
        f"\n[TrialAdapter] ===== Adaptation complete =====\n"
        f"[TrialAdapter] Total changes made: {changed_any}\n"
        f"[TrialAdapter] Changes breakdown:\n"
        f"  - Username replaced: {user_changed}\n"
        f"  - Password replaced: {pass_changed}\n"
        f"  - Navigation added: {nav_changed}\n"
        f"  - Login page wait added: {wait_changed}\n"
        f"  - Pause injected: {pause_changed}\n"
        f"  - MFA adjusted: {strip_changed}"
    )
    print(summary)
    logger.info(summary)
    
    if changed_any:
        logger.info("[TrialAdapter] Preview of adapted login section:")
        print("\n[TrialAdapter] Preview of adapted login section:")
        # Find and print the login section
        lines = updated.split('\n')
        for i, line in enumerate(lines):
            if 'userName.fill' in line or 'password.fill' in line:
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                preview = "\n".join(lines[start:end])
                print(preview)
                logger.info(preview)
                break
    
    return updated, changed_any


def prepare_trial_spec_path(spec_path: Path, repo_root: Path) -> Tuple[Path, Optional[Callable[[], None]]]:
    """Return a spec path to execute for trial runs; optionally provides cleanup callback."""
    try:
        original = spec_path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Trial adapter: failed to read spec %s (%s)", spec_path, exc)
        return spec_path, None

    adapted, changed = adapt_spec_content_for_trial(original, repo_root)
    if not changed:
        return spec_path, None

    temp_dir = spec_path.parent
    try:
        fd, temp_path_str = tempfile.mkstemp(
            prefix=spec_path.stem + "_trial_",
            suffix=".spec.ts",
            dir=temp_dir,
        )
        os.close(fd)
        temp_path = Path(temp_path_str)
        temp_path.write_text(adapted, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Trial adapter: failed to write adapted spec for %s (%s)", spec_path, exc)
        return spec_path, None

    def _cleanup() -> None:
        try:
            temp_path.unlink(missing_ok=True)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            logger.debug("Trial adapter: failed to remove temp spec %s", temp_path)

    return temp_path, _cleanup
