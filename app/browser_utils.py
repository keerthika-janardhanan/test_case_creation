"""Utility helpers for working with browser selection options."""

from __future__ import annotations

from difflib import get_close_matches
from typing import Sequence, Tuple

SUPPORTED_BROWSERS: Tuple[str, ...] = ("chromium", "firefox", "webkit")


def normalize_browser_name(browser_name: str, supported: Sequence[str] | None = None) -> str:
    """Return a canonical browser name or raise a helpful error.

    Parameters
    ----------
    browser_name:
        The user supplied browser identifier. Matching is case-insensitive and
        ignores leading/trailing whitespace.
    supported:
        The iterable of supported browser identifiers. When omitted the
        ``SUPPORTED_BROWSERS`` constant is used.

    Returns
    -------
    str
        The canonical browser identifier from ``supported``.

    Raises
    ------
    ValueError
        If ``browser_name`` is empty or does not correspond to a supported
        browser. When the input is close to a supported value, the exception
        message includes a suggestion to aid the caller.
    """

    if supported is None:
        supported = SUPPORTED_BROWSERS

    if browser_name is None:
        raise ValueError("Browser name cannot be empty.")

    normalized = browser_name.strip().lower()
    if not normalized:
        raise ValueError("Browser name cannot be empty.")

    canonical_map = {option.lower(): option for option in supported}
    if normalized in canonical_map:
        return canonical_map[normalized]

    matches = get_close_matches(normalized, list(canonical_map.keys()), n=1, cutoff=0.6)
    if matches:
        suggestion = canonical_map[matches[0]]
        raise ValueError(f"Unsupported browser '{browser_name}'. Did you mean '{suggestion}'?")

    options = ", ".join(canonical_map.values())
    raise ValueError(f"Unsupported browser '{browser_name}'. Choose from {options}.")


__all__ = ["SUPPORTED_BROWSERS", "normalize_browser_name"]
