"""SignalScout GUI entry point (Nuitka exe build).

v0.3.1: the exe runs with the console DISABLED, so any unhandled startup
exception used to be completely invisible - the process just never showed
a window (owner: "app exe nahi chal rahi"). Now:
- every launch appends a line to %LOCALAPPDATA%\\SignalScout\\crash.log
- every crash is reported via a native Windows message box (works even
  when tkinter itself failed to initialize) AND saved to crash.log
- Nuitka additionally mirrors stderr to %TEMP%\\SignalScout-stderr.log
  (see build-windows.yml --force-stderr-spec)
"""

import os
import sys
import time
import traceback

LOG_DIR = os.path.join(
    os.getenv("LOCALAPPDATA") or os.path.expanduser("~"), "SignalScout")


def _log(text: str) -> None:
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "crash.log"), "a",
                  encoding="utf-8") as handle:
            handle.write(text.rstrip() + "\n")
    except Exception:
        pass


def _alert(title: str, text: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)  # MB_ICONERROR
    except Exception:
        try:
            print(text)  # source runs (python run_gui.py)
        except Exception:
            pass


def main():
    _log("=== SignalScout GUI launch %s | py %s | frozen=%s ==="
         % (time.strftime("%Y-%m-%d %H:%M:%S"), sys.version.split()[0],
            bool(getattr(sys, "frozen", False))))
    try:
        from lead_scout.gui import main as gui_main
        gui_main()
        _log("clean exit")
    except SystemExit:
        _log("exit via SystemExit")
        raise
    except Exception:
        tb = traceback.format_exc()
        _log("CRASH:\n" + tb)
        _alert("SignalScout failed to start",
               tb[-1500:]
               + "\n\nFull log: " + LOG_DIR + "\\crash.log")
        raise


if __name__ == "__main__":
    main()
