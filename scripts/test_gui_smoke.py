"""Headless smoke test for the SignalScout GUI (Studio-exact design).

Verifies: window builds, brand bg assets load, ring+orb pre-rotation
frames render (24 each), animation indices advance, all five tabs build
and switch, and footer/header strings exist. Run under Xvfb on CI/Linux:

    xvfb-run -a python scripts/test_gui_smoke.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

import tkinter as tk

from lead_scout import gui


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    app = gui.ScoutApp(root)
    failures = []

    # Withdrawn windows never receive <Configure>; place the bg art the
    # way the real event would, then verify the animation state.
    app._draw_bg()

    # bg frames pre-rotated (Pillow available in this env)
    if len(app._ring_frames) != 24:
        failures.append(f"ring frames = {len(app._ring_frames)} (want 24)")
    if len(app._orb_frames) != 24:
        failures.append(f"orb frames = {len(app._orb_frames)} (want 24)")

    # animation indices advance
    app._animate_ring()
    if app._ring_frame != 1:
        failures.append(f"ring frame index = {app._ring_frame} (want 1)")
    for _ in range(40):
        app._animate_orb()
    if app._orb_tick_n == 0:
        failures.append("orb tick counter did not advance")

    # tabs build + switch
    for key in ("discover", "scraper", "linkedin", "results", "settings"):
        app.show_tab(key)
        if app.current_tab != key:
            failures.append(f"tab {key} did not activate")

    # brand strings (search the whole widget tree)
    def _has_text(widget, needle):
        try:
            if needle in str(widget.cget("text")):
                return True
        except Exception:
            pass
        return any(_has_text(child, needle)
                   for child in widget.winfo_children())

    for expected in ("SIGNAL ", "SCOUT", "3sverse.com", "SignalScout v"):
        if not _has_text(root, expected):
            failures.append(f"brand string missing: {expected}")

    # speeds match the website hero values
    if app._BG_RING_MS != 5000:
        failures.append("ring speed not 120s/turn")
    if app._ORB_PERIOD != 13.0 or app._ORB_AMP != 12:
        failures.append("orb float params off (want 12px / 13s)")

    root.destroy()
    if failures:
        print("FAIL:")
        for line in failures:
            print(" -", line)
        return 1
    print("GUI smoke test PASS: 24+24 frames, animations advance, "
          "5 tabs OK, brand strings OK, site speeds OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
