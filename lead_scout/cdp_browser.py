"""CDP trusted-input browser controller for SignalScout.

Drives a REAL Chrome/Edge window over the Chrome DevTools Protocol (CDP)
and interacts with pages through Input.dispatchMouseEvent /
Input.dispatchKeyEvent. Those events are produced by the browser engine
itself, so the page receives isTrusted="true" input exactly like a real
user's clicks - the only honest way to automate "trusted" interaction
(fabricated DOM events from JavaScript would be isTrusted=false).

Boundaries kept from the compliance-first design:
- The user logs into any account THEMSELVES, in the automated window.
  The tool never reads, stores, or injects credentials or cookies.
- No CAPTCHA solving and no challenge automation. When an anti-bot
  challenge appears, the browser window STAYS OPEN and the HUMAN solves
  it; the controller then polls for the challenge to clear and resumes
  automatically (wait_for_challenge_resolution). JavaScript-only
  managed challenges usually clear by themselves inside the real
  browser - the controller simply waits for the page it is already
  running. The tool never clicks, scripts, or bypasses the challenge.
- Human-like pacing everywhere: randomized pauses between page loads,
  eased mouse paths with jitter, slow scrolls - and hard rate limits.

Requires: websocket-client (pure Python, no compilation).
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import websocket

CHALLENGE_MARKERS = (
    "just a moment", "attention required", "verify you are human",
    "checking your browser", "captcha", "unusual activity",
    "authwall", "login required",
)

# Ephemeral debug port (0 = OS picks a random free port). A fixed
# 922x listening socket on every machine is a deterministic
# automation fingerprint that EDR software flags as suspicious on
# clean tools. The real port is discovered after launch from
# DevToolsActivePort inside the profile dir.
DEFAULT_PORT = 0

WINDOWS_BROWSER_PATHS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
)

POSIX_BROWSER_NAMES = (
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    "microsoft-edge",
)


def find_browser_exe() -> str:
    """Locate a real installed browser (Chrome preferred, then Edge)."""
    override = os.getenv("SCOUT_BROWSER_PATH", "")
    if override and os.path.exists(override):
        return override
    if sys.platform.startswith("win"):
        for path in WINDOWS_BROWSER_PATHS:
            if os.path.exists(path):
                return path
    else:
        for name in POSIX_BROWSER_NAMES:
            found = shutil.which(name)
            if found:
                return found
    return ""


@dataclass
class PageReport:
    """What one page visit produced (or why it produced nothing)."""
    url: str
    final_url: str = ""
    title: str = ""
    html: str = ""
    status: str = "ok"          # ok | blocked_challenge | navigation_error
    note: str = ""


class CDPError(RuntimeError):
    pass


class TrustedBrowser:
    """One real browser window, driven over CDP with trusted input.

    Usage:
        browser = TrustedBrowser()
        browser.start()
        session = browser.open_tab()
        browser.navigate(session, "https://example.com")
        browser.trusted_click(session, 400, 300)
        html = browser.html(session)
        browser.quit()
    """

    def __init__(self, port: int = DEFAULT_PORT, profile_dir: str = "",
                 headless: bool = False):
        self.port = port
        self.headless = headless
        self.profile_dir = profile_dir or os.path.expanduser(
            "~/.signalscout/browser-profile")
        self.exe = find_browser_exe()
        self._proc: subprocess.Popen | None = None
        self._ws = None
        self._msg_id = 0
        self._min_page_delay = 6.0     # hard rate limits (LinkedIn-friendly)
        self._max_page_delay = 12.0
        self._last_nav = 0.0

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        return bool(self.exe)

    def start(self) -> None:
        if not self.available:
            raise CDPError(
                "No Chrome/Edge found. Set SCOUT_BROWSER_PATH to your "
                "browser executable.")
        os.makedirs(self.profile_dir, exist_ok=True)
        # Remove any stale DevToolsActivePort from a previous run so the
        # ephemeral port discovery below only sees THIS launch's file.
        try:
            os.remove(os.path.join(self.profile_dir,
                                   "DevToolsActivePort"))
        except OSError:
            pass
        flags = [
            self.exe,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.profile_dir}",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-timer-throttling",
            "--window-size=1360,900",
        ]
        if self.headless:
            flags.append("--headless=new")
        flags.append("about:blank")
        self._proc = subprocess.Popen(
            flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._wait_devtools()

    def _devtools_port_file(self) -> int | None:
        """First line of DevToolsActivePort = the ephemeral debug port."""
        path = os.path.join(self.profile_dir, "DevToolsActivePort")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                first = fh.readline().strip()
        except OSError:
            return None
        return int(first) if first.isdigit() else None

    def _wait_devtools(self, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self.port == 0:                  # ephemeral: discover it
                discovered = self._devtools_port_file()
                if discovered is None:          # browser still booting
                    time.sleep(0.5)
                    continue
                self.port = discovered
            try:
                info = self._http_json(
                    f"http://127.0.0.1:{self.port}/json/version")
                ws_url = info["webSocketDebuggerUrl"]
                self._ws = websocket.create_connection(
                    ws_url, timeout=30, suppress_origin=True,
                    enable_multithread=True)
                return
            except Exception as exc:      # browser still booting
                last_error = exc
                time.sleep(0.5)
        raise CDPError(f"Browser DevTools endpoint never came up: {last_error}")

    @staticmethod
    def _http_json(url: str) -> dict:
        import urllib.request
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def quit(self) -> None:
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:
            pass
        self._ws = None
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=10)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        self._proc = None

    # ------------------------------------------------------------------
    # protocol plumbing
    # ------------------------------------------------------------------
    def _send(self, method: str, params: dict | None = None,
              session_id: str | None = None, timeout: float = 45.0) -> dict:
        if self._ws is None:
            raise CDPError("Browser is not connected.")
        self._msg_id += 1
        message = {"id": self._msg_id, "method": method,
                   "params": params or {}}
        if session_id:
            message["sessionId"] = session_id
        self._ws.send(json.dumps(message))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._ws.settimeout(max(0.5, deadline - time.monotonic()))
            try:
                raw = self._ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            try:
                event = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if event.get("id") == self._msg_id:
                if "error" in event:
                    raise CDPError(f"{method}: {event['error']}")
                return event.get("result", {})
        raise CDPError(f"{method}: timed out after {timeout}s")

    # ------------------------------------------------------------------
    # tabs / navigation
    # ------------------------------------------------------------------
    def open_tab(self, url: str = "about:blank") -> str:
        target = self._send("Target.createTarget",
                            {"url": url, "newWindow": False})
        session = self._send("Target.attachToTarget",
                             {"targetId": target["targetId"],
                              "flatten": True})["sessionId"]
        self._send("Page.enable", session_id=session)
        self._send("Runtime.enable", session_id=session)
        return session

    def _polite_page_delay(self) -> None:
        remaining = random.uniform(self._min_page_delay,
                                   self._max_page_delay) - (
            time.monotonic() - self._last_nav)
        if remaining > 0:
            time.sleep(remaining)

    def navigate(self, session: str, url: str,
                 settle_seconds: float = 2.0) -> PageReport:
        """Navigate with a human-like pause first, then wait for load."""
        self._polite_page_delay()
        try:
            self._send("Page.navigate", {"url": url}, session_id=session)
        except CDPError as exc:
            return PageReport(url, status="navigation_error", note=str(exc))
        self._last_nav = time.monotonic()
        deadline = time.monotonic() + 40.0
        ready = False
        while time.monotonic() < deadline:
            try:
                state = self.eval_js(
                    session, "document.readyState + '|' + location.href")
                if state and state.get("value", "").startswith("complete|"):
                    ready = True
                    break
            except CDPError:
                pass
            time.sleep(0.6)
        report = PageReport(url, status="ok" if ready else "navigation_error",
                            note="" if ready else "load timeout")
        if ready:
            report.final_url = str(state.get("value", "")).split("|", 1)[1]
            self.human_pause(1.0, 2.0)
            meta = self.eval_js(session, "document.title")
            report.title = str(meta.get("value", ""))
            time.sleep(settle_seconds)
        if self.looks_like_challenge(session, report):
            # Real browser + real engine: managed JS challenges usually
            # clear on their own. Watch for that first - no interaction.
            if self.wait_for_challenge_resolution(session, max_wait=75.0):
                report.final_url = str(self.eval_js(
                    session, "location.href").get("value", ""))
                report.title = str(self.eval_js(
                    session, "document.title").get("value", ""))
                report.status = "ok"
                report.note = "challenge self-cleared in the real browser"
                return report
            report.status = "blocked_challenge"
            report.html = ""
            report.note = ("challenge not cleared - solve it in the open "
                           "browser window; the tool never bypasses it")
        return report

    def looks_like_challenge(self, session: str, report: PageReport) -> bool:
        haystack = f"{report.final_url} {report.title}".lower()
        if any(marker in haystack for marker in CHALLENGE_MARKERS):
            return True
        try:
            marker_probe = self.eval_js(
                session,
                "(() => { const t = document.body ? "
                "document.body.innerText.slice(0, 4000).toLowerCase() : '';"
                " return ('just a moment' in t) || ('verify you are human' "
                "in t) || ('checking your browser' in t); })()")
            return bool(marker_probe.get("value"))
        except CDPError:
            return False

    def wait_for_challenge_resolution(self, session: str,
                                      max_wait: float = 150.0,
                                      progress=None) -> bool:
        """Wait for a HUMAN to clear the challenge in the open window.

        The real browser engine runs the challenge's own JavaScript (a
        managed challenge usually clears itself in a real browser, no
        human touch needed). If interaction is required, the human does
        it - this method only WATCHES and resumes when the page is
        clean. Returns True when the challenge cleared in time."""
        deadline = time.monotonic() + max_wait
        notified = False
        while time.monotonic() < deadline:
            probe = self.eval_js(
                session, "location.href + '||' + document.title")
            value = str(probe.get("value", ""))
            report = PageReport("", final_url=value.split("||")[0],
                                title="||".join(value.split("||")[1:]))
            if not self.looks_like_challenge(session, report):
                self.human_pause(1.0, 2.0)
                return True
            if not notified and progress:
                progress("Challenge shown - it often clears by itself; "
                         "solve it in the browser window if asked. "
                         "Waiting up to %.0fs…" % max_wait)
                notified = True
            time.sleep(2.5)
        return False

    # ------------------------------------------------------------------
    # evaluation
    # ------------------------------------------------------------------
    def eval_js(self, session: str, expression: str) -> dict:
        result = self._send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True,
             "awaitPromise": False},
            session_id=session)
        return result.get("result", {})

    def html(self, session: str) -> str:
        value = self.eval_js(
            session, "document.documentElement.outerHTML")
        return str(value.get("value", ""))

    # ------------------------------------------------------------------
    # trusted input (the whole point: isTrusted=true events)
    # ------------------------------------------------------------------
    def _mouse(self, session: str, kind: str, x: float, y: float,
               button: str = "none", click_count: int = 0,
               delta_y: float = 0.0) -> None:
        params = {"type": kind, "x": int(x), "y": int(y), "button": button}
        if click_count:
            params["clickCount"] = click_count
        if delta_y:
            params["deltaY"] = delta_y
        self._send("Input.dispatchMouseEvent", params, session_id=session)

    def move_mouse(self, session: str, x0: float, y0: float,
                   x1: float, y1: float) -> None:
        """Eased, jittered multi-step move - the natural lead-in to a
        trusted click. Returns the final resting coordinates."""
        steps = random.randint(14, 24)
        # slight overshoot then settle (humans rarely stop dead-on)
        ox = x1 + random.uniform(-6, 6)
        oy = y1 + random.uniform(-5, 5)
        for step in range(1, steps + 2):
            t = step / (steps + 1)
            eased = t * (2 - t)                     # ease-out quad
            x = x0 + (ox - x0) * eased + random.uniform(-1.5, 1.5)
            y = y0 + (oy - y0) * eased + random.uniform(-1.2, 1.2)
            self._mouse(session, "mouseMoved", x, y)
            time.sleep(random.uniform(0.008, 0.028))
        for step in range(3):                       # settle back to target
            t = (step + 1) / 3
            x = ox + (x1 - ox) * t
            y = oy + (y1 - oy) * t
            self._mouse(session, "mouseMoved", x, y)
            time.sleep(0.012)

    def trusted_click(self, session: str, x: float, y: float,
                      from_x: float | None = None,
                      from_y: float | None = None) -> None:
        """Trusted click: eased approach + press + release. The page
        receives isTrusted=true mousedown/mouseup/click."""
        if from_x is None or from_y is None:
            from_x = random.uniform(60, 420)
            from_y = random.uniform(60, 320)
        self.move_mouse(session, from_x, from_y, x, y)
        self._mouse(session, "mousePressed", x, y, button="left",
                    click_count=1)
        time.sleep(random.uniform(0.05, 0.13))      # human press duration
        self._mouse(session, "mouseReleased", x, y, button="left",
                    click_count=1)
        self.human_pause(0.4, 1.2)

    def scroll(self, session: str, x: float, y: float, amount: float) -> None:
        """Trusted mouse-wheel scroll in small human chunks."""
        remaining = amount
        direction = 1 if remaining >= 0 else -1
        while abs(remaining) > 1:
            chunk = direction * min(abs(remaining),
                                    random.uniform(120, 320))
            self._mouse(session, "mouseWheel", x, y, delta_y=chunk)
            remaining -= chunk
            time.sleep(random.uniform(0.15, 0.5))

    def type_text(self, session: str, text: str, focus_first: str = "") -> None:
        """Trusted typing. focus_first may hold a JS snippet that returns
        the screen position of an element to click first (e.g.
        elementBoxCenter(session, 'input[name=q]'))."""
        if focus_first:
            pos = self.eval_js(session, focus_first)
            value = pos.get("value")
            if isinstance(value, dict) and "x" in value:
                self.trusted_click(session, value["x"], value["y"])
        self._send("Input.insertText", {"text": text}, session_id=session)
        self.human_pause(0.3, 0.8)

    def press_enter(self, session: str) -> None:
        for params in (
            {"type": "rawKeyDown", "key": "Enter",
             "windowsVirtualKeyCode": 13, "code": "Enter"},
            {"type": "keyUp", "key": "Enter",
             "windowsVirtualKeyCode": 13, "code": "Enter"},
        ):
            self._send("Input.dispatchKeyEvent", params, session_id=session)
            time.sleep(random.uniform(0.04, 0.1))

    # ------------------------------------------------------------------
    # helpers used by providers
    # ------------------------------------------------------------------
    def human_pause(self, lo: float, hi: float) -> None:
        time.sleep(random.uniform(lo, hi))

    def element_box_center_js(self, css_selector: str) -> str:
        """JS snippet (for type_text focus_first) that clicks nothing by
        itself but returns the viewport center of an element."""
        safe = json.dumps(css_selector)
        return (
            f"(() => {{ const el = document.querySelector({safe});"
            " if (!el) return null;"
            " const r = el.getBoundingClientRect();"
            " return {x: r.left + r.width / 2, y: r.top + r.height / 2};"
            " })()"
        )

    def slow_read(self, session: str, screens: int = 2) -> None:
        """Scroll down like a person reading, then back up a touch."""
        self.scroll(session, random.uniform(300, 700),
                    random.uniform(200, 500), 620 * screens)
        self.human_pause(0.8, 1.6)
        self.scroll(session, 400, 300, -180)

    # ------------------------------------------------------------------
    # context manager
    # ------------------------------------------------------------------
    def __enter__(self) -> TrustedBrowser:
        self.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.quit()


def same_site(url_a: str, url_b: str) -> bool:
    return urlparse(url_a).netloc.lower() == urlparse(url_b).netloc.lower()
