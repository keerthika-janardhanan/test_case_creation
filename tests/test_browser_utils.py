from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.browser_utils import SUPPORTED_BROWSERS, normalize_browser_name


def test_normalize_browser_accepts_supported_variants():
    assert normalize_browser_name("chromium") == "chromium"
    assert normalize_browser_name("Chromium") == "chromium"
    assert normalize_browser_name(" firefox  ") == "firefox"


def test_normalize_browser_corrects_close_match():
    assert normalize_browser_name("chorium") == "chromium"


def test_normalize_browser_lists_supported_options_when_unknown():
    with pytest.raises(ValueError) as excinfo:
        normalize_browser_name("safari")
    message = str(excinfo.value)
    for browser in SUPPORTED_BROWSERS:
        assert browser in message


def test_normalize_browser_rejects_empty_values():
    with pytest.raises(ValueError):
        normalize_browser_name("")
