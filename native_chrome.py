"""Native Windows chrome helpers shared by 3S Verse desktop apps."""
from __future__ import annotations

import ctypes
import os


def _colourref(value: str) -> int:
    value = value.lstrip("#")
    red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return red | (green << 8) | (blue << 16)


def apply_dark_titlebar(window) -> None:
    if os.name != "nt":
        return
    try:
        window.update_idletasks()
        hwnd = int(window.winfo_id())
        user32 = ctypes.windll.user32
        parent = user32.GetParent(hwnd)
        while parent:
            hwnd = parent
            parent = user32.GetParent(hwnd)
        dwm = ctypes.windll.dwmapi
        enabled = ctypes.c_int(1)
        if dwm.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(enabled), ctypes.sizeof(enabled)) != 0:
            dwm.DwmSetWindowAttribute(
                hwnd, 19, ctypes.byref(enabled), ctypes.sizeof(enabled))
        for attribute, colour in (
                (35, "#090d26"), (36, "#ffffff"), (34, "#090d26")):
            value = ctypes.c_uint(_colourref(colour))
            dwm.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
        user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0,
            0x0001 | 0x0002 | 0x0004 | 0x0020 | 0x0040)
    except Exception:
        pass


def install_dark_titlebar(window) -> None:
    apply_dark_titlebar(window)
    try:
        window.after(120, lambda: apply_dark_titlebar(window))
    except Exception:
        pass
