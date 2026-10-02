"""Pure-math / marker tests for the CDP module (no browser needed)."""

from lead_scout.cdp_browser import (
    CHALLENGE_MARKERS,
    WINDOWS_BROWSER_PATHS,
    find_browser_exe,
)


def test_challenge_markers_cover_common_walls():
    joined = " ".join(CHALLENGE_MARKERS)
    for needle in ("authwall", "captcha", "just a moment"):
        assert needle in joined


def test_find_browser_returns_string():
    result = find_browser_exe()
    assert isinstance(result, str)
    # On a machine with no browser the tool reports gracefully (empty).
    # On Windows the standard install paths are probed first.
    if result:
        assert "\\" in result or "/" in result


def test_windows_path_list_nonempty():
    assert len(WINDOWS_BROWSER_PATHS) >= 4
