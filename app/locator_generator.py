import re
from typing import List


def _extract_string_arg(s: str) -> str | None:
    m = re.search(r"\(\s*['\"](.*?)['\"]", s)
    return m.group(1) if m else None


def _extract_role_and_name(s: str) -> tuple[str | None, str | None]:
    role = None
    name = None
    m_role = re.search(r"getByRole\(\s*['\"](.*?)['\"]", s)
    if m_role:
        role = m_role.group(1)
    m_name = re.search(r"name\s*:\s*['\"](.*?)['\"]", s)
    if m_name:
        name = m_name.group(1)
    return role, name


def _escape(text: str) -> str:
    # Simple XPath string literal escape that handles quotes by using concat if needed
    if "'" not in text:
        return f"'{text}'"
    if '"' not in text:
        return f'"{text}"'
    parts = []
    for part in text.split("'"):
        parts.append(f"'{part}'")
        parts.append('"' + "'" + '"')
    parts.pop()  # remove last added quote concat
    return "concat(" + ", ".join(parts) + ")"


def generate_xpath_candidates(selector_expr: str) -> List[str]:
    """
    Convert a Playwright selector expression like `page.getByText('Save')` or
    `page.getByRole('button', { name: 'Save' })` into a set of resilient XPath
    candidates including parent/sibling anchored variants suitable for Oracle
    Fusion UIs that change ids across patches.
    """
    s = selector_expr
    cands: list[str] = []

    # 1) Direct getByText
    if "getByText(" in s:
        text = _extract_string_arg(s)
        if text:
            esc = _escape(text.strip())
            cands.append(f"//*[normalize-space(.)={esc}]")
            # label -> input sibling pattern
            cands.append(
                f"//label[normalize-space(.)={esc}]/following::*[self::input or self::textarea or self::select][1]"
            )
            # parent anchored descendant
            cands.append(
                f"//*[normalize-space(.)={esc}]/ancestor::*[self::section or self::div or self::td or self::li][1]//*[self::input or self::button or self::a or self::span]"
            )

    # 2) getByRole with name
    elif "getByRole(" in s:
        role, name = _extract_role_and_name(s)
        role = (role or "").lower()
        esc_name = _escape(name.strip()) if name else None

        if role == "button":
            if esc_name:
                cands.append(f"//button[normalize-space(.)={esc_name}]")
                cands.append(f"//*[@role='button' and normalize-space(.)={esc_name}]")
                cands.append(
                    f"//span[normalize-space(.)={esc_name}]/ancestor::*[self::button or self::a][1]"
                )
            else:
                cands.append("//button | //*[@role='button']")

        elif role in {"link", "menuitem", "tab"}:
            if esc_name:
                cands.append(f"//a[normalize-space(.)={esc_name}] | //*[@role='{role}' and normalize-space(.)={esc_name}]")
            else:
                cands.append(f"//*[@role='{role}']")

        elif role in {"textbox", "combobox", "searchbox", "spinbutton"}:
            # try by associated label name first if provided
            if esc_name:
                cands.append(
                    f"//label[normalize-space(.)={esc_name}]/following::*[self::input or self::textarea or self::select][1]"
                )
            # generic role-based fallback
            cands.append(f"//*[@role='{role}']")

        else:
            if esc_name:
                cands.append(f"//*[@role='{role}' and normalize-space(.)={esc_name}]")
            else:
                cands.append(f"//*[@role='{role}']")

    # 3) getByLabel
    elif "getByLabel(" in s:
        label = _extract_string_arg(s)
        if label:
            esc = _escape(label.strip())
            cands.append(
                f"//label[normalize-space(.)={esc}]/following::*[self::input or self::textarea or self::select][1]"
            )
            cands.append(
                f"//*[@aria-label and normalize-space(@aria-label)={esc}] | //*[@placeholder and normalize-space(@placeholder)={esc}]"
            )

    # 4) getByTitle
    elif "getByTitle(" in s:
        title = _extract_string_arg(s)
        if title:
            esc = _escape(title.strip())
            cands.append(f"//*[@title and normalize-space(@title)={esc}]")

    # 5) locator('xpath=...') or locator('css=...')
    elif "locator(" in s:
        m = re.search(r"locator\(\s*['\"](.*?)['\"]\s*\)", s)
        if m:
            inner = m.group(1)
            if inner.startswith("xpath="):
                cands.append(inner.replace("xpath=", ""))
            elif inner.startswith("oracle-xpath="):
                cands.append(inner.replace("oracle-xpath=", ""))
            elif inner.startswith("text="):
                txt = inner.split("=", 1)[1]
                cands.append(f"//*[contains(normalize-space(.), {_escape(txt)})]")
            elif inner.startswith("css="):
                # No DOM to translate robustly; keep a generic attribute-based fallback
                cands.append("//*[@id or @class or @data-testid][1]")

    # 6) Final generic fallbacks leveraging Oracle Fusion id patterns
    # If nothing captured above, try a few robust patterns
    if not cands:
        cands.append("//*[@data-testid or @aria-label or @title]")
        cands.append("//*[contains(@id, ':')]")  # Oracle ADF-style ids often contain ':'

    # Deduplicate while preserving order
    seen = set()
    uniq: list[str] = []
    for x in cands:
        if x not in seen:
            uniq.append(x)
            seen.add(x)
    return uniq


def to_union_xpath(candidates: List[str]) -> str:
    """Join candidates using XPath union for resilient matching."""
    if not candidates:
        return "//unknown"
    return " | ".join(candidates)
