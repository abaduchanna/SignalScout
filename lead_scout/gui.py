"""SignalScout GUI - Studio-exact desktop app for wireless retail leads.

Same 3sverse.com dark-hero design system as License Studio: identical
brand tokens, buttons, eyebrows, stacked hero header, brand footer, and
the animated ring+orb background (site speeds: ring 120s/turn, orb
140s/turn + 12px/13s float). Developed by www.3SVerse.com.

Tabs: Discover (Google Places) · Web Scraper (MechanicalSoup /
BeautifulSoup / browser-fingerprint mode) · LinkedIn (CDP trusted
input) · Results · Settings. All user-facing strings ENGLISH ONLY.
"""

from __future__ import annotations

import json
import math
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

try:
    from PIL import Image as _PILImage
    from PIL import ImageTk as _PILImageTk
except Exception:
    _PILImage = None
    _PILImageTk = None

# v0.3.1: heavy scraping imports are ISOLATED. The frozen exe runs with
# the console disabled, so if any optional dependency failed to load, the
# old module-level import killed the process BEFORE the window even
# opened - a completely silent death (owner: "app exe nahi chal rahi").
# Now the GUI always opens; a missing dependency is reported with the
# exact error the moment a job starts.
_IMPORT_ERR = None
try:
    from .crawler import PublicSiteCrawler
    from .providers.dealer_locator import search_locator_cdp, search_locator_mechanical
    from .providers.google_places import search_places
    from .providers.linkedin_cdp import find_company_urls, scrape_companies
    from .providers.search_engine_discovery import find_company_urls_via_search
except Exception:                                   # frozen-exe safety net
    import traceback as _traceback
    _IMPORT_ERR = _traceback.format_exc()
from native_chrome import install_dark_titlebar

from .markets import sweep_queries
from .storage import dedupe, write_csv, write_xlsx

# ── Brand tokens: the 3sverse.com dark-hero palette (index.css .dark) ──
BG = "#07060b"
PANEL = "#0d0c14"
FIELD = "#12101a"
BORDER = "#232130"
TEXT = "#f5f1e6"
DIM = "#9b97b3"
CYAN = "#6ee7ef"
PERI = "#78a6ff"
MAGENTA = "#e44bd7"
LIME = "#c7ef70"
ACCENT = CYAN
ACCENT_HOVER = "#9deff5"
DANGER = "#ef6a52"
ERR = DANGER
OK = LIME
WARN = "#f5c518"
GRAD = (CYAN, PERI, MAGENTA)
FONT = "Segoe UI"
MONO = "Consolas"
HEAD_FONT = FONT

VERSION = "0.3.3"

SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".signalscout",
                             "settings.json")


def _probe_fonts(root):
    """Brand families Montserrat / DM Mono with graceful fallbacks."""
    global FONT, MONO, HEAD_FONT
    try:
        import tkinter.font as _tkf
        fams = set(_tkf.families(root))
        if "Montserrat" in fams:
            FONT = HEAD_FONT = "Montserrat"
        if "DM Mono" in fams:
            MONO = "DM Mono"
        elif "JetBrains Mono" in fams:
            MONO = "JetBrains Mono"
    except Exception:
        pass


def _hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t):
    ca, cb = _hex_rgb(a), _hex_rgb(b)
    return "#%02x%02x%02x" % tuple(
        int(round(ca[i] + (cb[i] - ca[i]) * t)) for i in range(3))


def grad_color(t):
    """CYAN -> PERI -> MAGENTA across t in [0,1]."""
    t = min(1.0, max(0.0, t))
    if t <= 0.5:
        return _mix(GRAD[0], GRAD[1], t * 2)
    return _mix(GRAD[1], GRAD[2], (t - 0.5) * 2)


def make_grad_bar(parent, height=3):
    """Thin full-width tri-gradient bar (site scroll-progress signature)."""
    c = tk.Canvas(parent, bg=BG, highlightthickness=0, bd=0, height=height)

    def _draw(_e=None):
        c.delete("all")
        w = max(int(c.winfo_width() or 1), 2)
        for x in range(0, w, 2):
            c.create_rectangle(x, 0, x + 2, height, outline="",
                               fill=grad_color(x / float(w - 1)))
    c.bind("<Configure>", _draw)
    return c


def make_btn(parent, text, command, kind="ghost", size=9, padx=16, pady=7):
    """Uniform brand button (same geometry as License Studio)."""
    s = {"primary": (CYAN, "#07060b", ACCENT_HOVER, "#07060b", BORDER),
         "ghost": ("#16141f", TEXT, "#242231", CYAN, BORDER),
         "soft": ("#16141f", LIME, "#242231", LIME, BORDER),
         "warn": ("#16141f", WARN, "#242231", WARN, BORDER),
         "danger": ("#16141f", DANGER, DANGER, "#07060b", BORDER)}[kind]
    b = tk.Button(parent, text=text, command=command, bd=0, relief="flat",
                  cursor="hand2", font=(FONT, size, "bold"),
                  padx=padx, pady=pady, highlightthickness=1,
                  bg=s[0], fg=s[1], activebackground=s[2],
                  activeforeground=s[3], highlightbackground=s[4])
    b.bind("<Enter>", lambda _e: b.config(bg=s[2], fg=s[3]))
    b.bind("<Leave>", lambda _e: b.config(bg=s[0], fg=s[1]))
    return b


def make_eyebrow(parent, text, color=CYAN, bg=PANEL):
    """The site's mono-tech uppercase section labels."""
    return tk.Label(parent, text=text.upper(), bg=bg, fg=color,
                    font=(MONO, 8, "bold"))


def asset_path(name: str) -> str:
    """Locate bundled brand art (works from source and frozen exe)."""
    bases = []
    if getattr(sys, "frozen", False):
        bases.append(os.path.dirname(os.path.abspath(sys.executable)))
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            bases.append(meipass)
    bases.append(os.path.dirname(os.path.abspath(__file__)))
    bases.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              os.pardir))
    for base in bases:
        candidate = os.path.join(base, name)
        if os.path.exists(candidate):
            return candidate
        candidate = os.path.join(base, "assets", name)
        if os.path.exists(candidate):
            return candidate
    return ""


def load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def save_settings(settings: dict) -> None:
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2)
    except Exception:
        pass


class ScoutApp:
    def __init__(self, root):
        self.root = root
        root.title("SignalScout %s" % VERSION)
        root.configure(bg=BG)
        root.geometry("900x780")
        root.minsize(860, 740)
        _probe_fonts(root)
        try:
            ico = asset_path("3sverse_icon.ico")
            if ico and sys.platform.startswith("win"):
                root.iconbitmap(default=ico)
        except Exception:
            pass
        install_dark_titlebar(root)

        # Brand background - identical composition + speeds as Studio.
        self._bg_canvas = tk.Canvas(root, bg=BG, highlightthickness=0,
                                    bd=0)
        self._bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._bg_canvas.bind("<Configure>", lambda _e: self._draw_bg())
        self._bg_imgs = []
        self._RING_FRAMES = 24
        self._RING_MAX = 600
        self._BG_RING_MS = 5000          # 24 x 5s = 120s / rotation
        self._ORB_TICK_MS = 40
        self._ORB_AMP = 12               # site floatY
        self._ORB_PERIOD = 13.0          # site floatDur
        self._ORB_SPIN_TICKS = 146       # 146 x 40ms x 24 = 140s / rotation
        self._ORB_MAX = 460
        self._RING_FLOAT_AMP = 16        # WiFi Transfer bgfloatR
        self._RING_FLOAT_PERIOD = 12.0
        self._ring_frames = []
        self._orb_frames = []
        self._ring_item = None
        self._orb_item = None
        self._ring_frame = 0
        self._orb_frame = 0
        self._orb_tick_n = 0
        self._orb_phase = 0.0
        self._ring_phase = 0.0
        self._ring_x = 0.0
        self._ring_base_y = 0.0
        self._orb_x = 0.0
        self._orb_base_y = 0.0
        self._load_bg_assets()

        self._q = queue.Queue()
        self.settings = load_settings()
        self.current_tab = "discover"
        self._leads = []                 # all collected Lead records
        self._busy = False
        self._browser = None             # TrustedBrowser (LinkedIn tab)
        self._browser_session = None

        self._build_header()
        self._build_footer()
        self._build_tabs()
        self._build_discover_tab()
        self._build_scraper_tab()
        self._build_linkedin_tab()
        self._build_results_tab()
        self._build_settings_tab()
        self.show_tab("discover")
        self.root.after(100, self._poll)
        self.root.after(self._BG_RING_MS, self._animate_ring)
        self.root.after(self._ORB_TICK_MS, self._animate_orb)

    # ------------------------------------------------------------------
    # brand background (same ring/orb artwork as the 3sverse.com hero)
    # ------------------------------------------------------------------
    def _load_bg_assets(self):
        for name in ("bg_ring.png", "bg_orb.png"):
            path = asset_path(name)
            try:
                if path:
                    self._bg_imgs.append(tk.PhotoImage(file=path))
            except Exception:
                pass
        if _PILImage is not None and self._bg_imgs:
            try:
                src = _PILImage.open(asset_path("bg_ring.png")).convert("RGBA")
                src.putalpha(src.getchannel("A").point(
                    lambda value: min(255, int(value * 1.55))))
                if max(src.size) > self._RING_MAX:
                    sc = self._RING_MAX / float(max(src.size))
                    src = src.resize((max(1, int(src.width * sc)),
                                      max(1, int(src.height * sc))),
                                     _PILImage.LANCZOS)
                self._ring_frames = [
                    _PILImageTk.PhotoImage(
                        src.rotate(int(round(i * 360.0 / self._RING_FRAMES)),
                                   resample=_PILImage.BICUBIC, expand=False))
                    for i in range(self._RING_FRAMES)]
            except Exception:
                self._ring_frames = []
        if _PILImage is not None and len(self._bg_imgs) > 1:
            try:
                src = _PILImage.open(asset_path("bg_orb.png")).convert("RGBA")
                src.putalpha(src.getchannel("A").point(
                    lambda value: min(255, int(value * 1.55))))
                if max(src.size) > self._ORB_MAX:
                    sc = self._ORB_MAX / float(max(src.size))
                    src = src.resize((max(1, int(src.width * sc)),
                                      max(1, int(src.height * sc))),
                                     _PILImage.LANCZOS)
                self._orb_frames = [
                    _PILImageTk.PhotoImage(
                        src.rotate(int(round(i * 360.0 / self._RING_FRAMES)),
                                   resample=_PILImage.BICUBIC, expand=False))
                    for i in range(self._RING_FRAMES)]
            except Exception:
                self._orb_frames = []

    def _draw_bg(self):
        c = self._bg_canvas
        c.delete("all")
        w = c.winfo_width() or 820
        h = c.winfo_height() or 640
        orb = (self._orb_frames[0] if self._orb_frames else
               (self._bg_imgs[1] if len(self._bg_imgs) > 1 else None))
        frames = self._ring_frames
        if frames:
            self._ring_x = w + frames[0].width() * 0.05
            self._ring_base_y = h * 0.44
            self._ring_item = c.create_image(
                self._ring_x, self._ring_base_y,
                image=frames[self._ring_frame], anchor="center")
        elif self._bg_imgs:
            ring = self._bg_imgs[0]
            self._ring_x = w + ring.width() * 0.05
            self._ring_base_y = h * 0.44
            self._ring_item = c.create_image(
                self._ring_x, self._ring_base_y,
                image=ring, anchor="center")
        else:
            self._ring_item = None
        if not frames and len(self._bg_imgs) < 2:
            cy = h * 0.46
            for r in (120, 185, 250, 315):
                c.create_oval(w - r, cy - r, w + r, cy + r,
                              outline=BORDER, width=1)
        if orb is not None:
            self._orb_x = -orb.width() * 0.10
            self._orb_base_y = h - orb.height() * 0.32
            self._orb_item = c.create_image(
                self._orb_x, self._orb_base_y, image=orb, anchor="center")
        else:
            self._orb_item = None

    def _animate_ring(self):
        try:
            if self.root.state() != "iconic":
                if self._ring_frames and self._ring_item is not None:
                    self._ring_frame = (self._ring_frame + 1) % len(
                        self._ring_frames)
                    self._bg_canvas.itemconfig(
                        self._ring_item,
                        image=self._ring_frames[self._ring_frame])
        except Exception:
            pass
        self.root.after(self._BG_RING_MS, self._animate_ring)

    def _animate_orb(self):
        try:
            if self.root.state() != "iconic":
                if self._orb_item is not None:
                    step = 2 * math.pi * (self._ORB_TICK_MS / 1000.0) \
                        / self._ORB_PERIOD
                    self._orb_phase = (self._orb_phase + step) % (2 * math.pi)
                    dy = math.sin(self._orb_phase) * self._ORB_AMP
                    self._bg_canvas.coords(
                        self._orb_item, self._orb_x, self._orb_base_y + dy)
                    ring_step = 2 * math.pi * (self._ORB_TICK_MS / 1000.0) \
                        / self._RING_FLOAT_PERIOD
                    self._ring_phase = (self._ring_phase + ring_step) % (2 * math.pi)
                    if self._ring_item is not None:
                        ring_dy = math.sin(self._ring_phase) * self._RING_FLOAT_AMP
                        self._bg_canvas.coords(
                            self._ring_item, self._ring_x,
                            self._ring_base_y + ring_dy)
                    self._orb_tick_n += 1
                    if (self._orb_frames and self._orb_tick_n
                            >= self._ORB_SPIN_TICKS):
                        self._orb_tick_n = 0
                        self._orb_frame = (self._orb_frame + 1) % len(
                            self._orb_frames)
                        self._bg_canvas.itemconfig(
                            self._orb_item,
                            image=self._orb_frames[self._orb_frame])
        except Exception:
            pass
        self.root.after(self._ORB_TICK_MS, self._animate_orb)

    # ------------------------------------------------------------------
    # shell
    # ------------------------------------------------------------------
    def _build_header(self):
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=18, pady=(14, 0))
        logo = asset_path("3sverse_logo_header.png")
        try:
            if logo:
                self._hdr_logo = tk.PhotoImage(file=logo)
                tk.Label(head, image=self._hdr_logo, bg=BG,
                         bd=0).pack(anchor="center")
        except Exception:
            pass
        trow = tk.Frame(head, bg=BG)
        trow.pack(anchor="center")
        tk.Label(trow, text="SIGNAL ", bg=BG, fg=TEXT,
                 font=(HEAD_FONT, 20)).pack(side="left")
        tk.Label(trow, text="SCOUT", bg=BG, fg=CYAN,
                 font=(HEAD_FONT, 20)).pack(side="left")
        make_eyebrow(head, "VidaPay dealer tools · Total Wireless retail "
                           "leads", color=CYAN, bg=BG).pack(
                               anchor="center", pady=(4, 0))
        make_grad_bar(self.root).pack(fill="x", padx=0, pady=(10, 0))

    def _build_footer(self):
        bar = tk.Frame(self.root, bg=PANEL,
                       highlightbackground=BORDER, highlightthickness=1)
        bar.pack(side="bottom", fill="x")
        tk.Frame(bar, bg=PANEL, height=30).pack(fill="x")
        tk.Label(bar, text="Independent vendor — not affiliated with "
                           "VidaPay", bg=PANEL, fg=DIM,
                 font=(FONT, 8)).place(relx=0.0, rely=0.5, anchor="w", x=18)
        tk.Label(bar, text="© %d 3S Verse · Developed by www.3sverse.com"
                 % time.localtime().tm_year, bg=PANEL, fg=DIM,
                 font=(FONT, 8)).place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(bar, text="SignalScout v%s" % VERSION,
                 bg=PANEL, fg=DIM, font=(MONO, 8)).place(
                     relx=1.0, rely=0.5, anchor="e", x=-18)

    def _build_tabs(self):
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=18, pady=(10, 2))
        self._tab_buttons = {}
        for key, label in (("discover", "Discover"),
                           ("scraper", "Web Scraper"),
                           ("linkedin", "LinkedIn"),
                           ("results", "Results"),
                           ("settings", "Settings")):
            b = tk.Button(bar, text=label, bd=0, relief="flat",
                          cursor="hand2", font=(FONT, 10, "bold"),
                          padx=18, pady=8, bg=PANEL, fg=DIM,
                          activebackground="#242231", activeforeground=CYAN,
                          highlightthickness=0,
                          command=lambda k=key: self.show_tab(k))
            b.pack(side="left")
            b.bind("<Enter>", lambda _e, k=key, bb=b:
                   bb.config(fg=TEXT) if self.current_tab != k else None)
            b.bind("<Leave>", lambda _e, k=key, bb=b:
                   bb.config(fg=DIM) if self.current_tab != k else None)
            self._tab_buttons[key] = b
        self.hdr_count = tk.Label(bar, text="", bg=BG, fg=OK,
                                  font=(MONO, 8, "bold"))
        self.hdr_count.pack(side="right")
        self._tab_frames = {}

    def show_tab(self, key):
        self.current_tab = key
        for k, b in self._tab_buttons.items():
            active = (k == key)
            b.configure(bg=("#242231" if active else PANEL),
                        fg=(CYAN if active else DIM))
        for k, f in self._tab_frames.items():
            if k == key:
                f.pack(fill="both", expand=True, padx=18, pady=(8, 12))
            else:
                f.pack_forget()
        if key == "results":
            self._refresh_results()

    def _tab(self, key):
        f = tk.Frame(self.root, bg=BG)
        self._tab_frames[key] = f
        return f

    def _panel(self, parent, title=None, sub=None):
        p = tk.Frame(parent, bg=PANEL, highlightbackground=BORDER,
                     highlightthickness=1)
        if title:
            make_eyebrow(p, title).pack(anchor="w", padx=12,
                                        pady=(10, 1))
            if sub:
                tk.Label(p, text=sub, bg=PANEL, fg=DIM,
                         font=(FONT, 8)).pack(anchor="w", padx=12,
                                              pady=(0, 4))
        return p

    # ------------------------------------------------------------------
    # shared plumbing
    # ------------------------------------------------------------------
    def _poll(self):
        try:
            while True:
                job, payload = self._q.get_nowait()
                job(payload)
        except queue.Empty:
            pass
        except Exception:
            pass
        self.root.after(120, self._poll)

    def log(self, widget, message, color=None):
        widget.configure(state="normal")
        tag = "err" if color == ERR else ("ok" if color == OK else "info")
        widget.insert("end", message + "\n", tag)
        widget.see("end")
        widget.configure(state="disabled")

    def _make_log(self, parent, height=9):
        box = tk.Text(parent, bg=FIELD, fg=TEXT, relief="flat",
                      font=(MONO, 8), height=height, wrap="word",
                      insertbackground=TEXT, highlightthickness=1,
                      highlightbackground=BORDER, bd=0)
        box.tag_configure("err", foreground=ERR)
        box.tag_configure("ok", foreground=OK)
        box.tag_configure("info", foreground=DIM)
        box.configure(state="disabled")
        return box

    def _busy_start(self, button, label, note):
        button.configure(state="disabled", text="Working…")
        label.configure(text=note, fg=WARN)

    def _busy_end(self, button, label, note, good=True):
        button.configure(state="normal")
        label.configure(text=note, fg=(OK if good else ERR))

    # ------------------------------------------------------------------
    # discover tab (Google Places)
    # ------------------------------------------------------------------
    def _build_discover_tab(self):
        f = self._tab("discover")
        top = self._panel(f, "Discover businesses",
                          "Official Google Places API · single market or "
                          "ALL-USA sweep (one narrow query per state + DC)")
        top.pack(fill="x")
        grid = tk.Frame(top, bg=PANEL)
        grid.pack(fill="x", padx=12, pady=(4, 12))
        grid.columnconfigure(1, weight=1)

        tk.Label(grid, text="Search query", bg=PANEL, fg=DIM,
                 font=(FONT, 9)).grid(row=0, column=0, sticky="w", pady=3)
        self.dq_var = tk.StringVar(
            value="Total Wireless retailer in Houston TX")
        tk.Entry(grid, textvariable=self.dq_var, bg=FIELD, fg=TEXT,
                 relief="flat", insertbackground=TEXT, font=(FONT, 10),
                 highlightbackground=BORDER, highlightthickness=1
                 ).grid(row=0, column=1, sticky="we", pady=3, ipady=4)

        tk.Label(grid, text="Places API key", bg=PANEL, fg=DIM,
                 font=(FONT, 9)).grid(row=1, column=0, sticky="w", pady=3)
        self.dkey_var = tk.StringVar(
            value=str(self.settings.get("places_api_key", "")))
        tk.Entry(grid, textvariable=self.dkey_var, bg=FIELD, fg=TEXT,
                 relief="flat", insertbackground=TEXT, font=(FONT, 10),
                 show="*", highlightbackground=BORDER, highlightthickness=1
                 ).grid(row=1, column=1, sticky="we", pady=3, ipady=4)

        orow = tk.Frame(grid, bg=PANEL)
        orow.grid(row=2, column=0, columnspan=2, sticky="w", pady=3)
        tk.Label(orow, text="Result pages (20 each)", bg=PANEL, fg=DIM,
                 font=(FONT, 9)).pack(side="left")
        self.dpages_var = tk.IntVar(value=1)
        tk.Spinbox(orow, from_=1, to=3, width=4, textvariable=self.dpages_var,
                   bg=FIELD, fg=TEXT, relief="flat", insertbackground=TEXT,
                   buttonbackground=PANEL, font=(FONT, 9),
                   highlightbackground=BORDER, highlightthickness=1
                   ).pack(side="left", padx=(8, 16))
        self.denrich_var = tk.BooleanVar(value=True)
        tk.Checkbutton(orow, text="Enrich found websites after discovery",
                       variable=self.denrich_var, bg=PANEL, fg=TEXT,
                       activebackground=PANEL, activeforeground=TEXT,
                       selectcolor=FIELD, font=(FONT, 9), relief="flat",
                       bd=0, highlightthickness=0).pack(side="left")
        srow = tk.Frame(grid, bg=PANEL)
        srow.grid(row=3, column=0, columnspan=2, sticky="w", pady=3)
        tk.Label(srow, text="Scope", bg=PANEL, fg=DIM,
                 font=(FONT, 9)).pack(side="left")
        self.dscope_var = tk.StringVar(value="single")
        for value, label in (
                ("single", "Single market (query above)"),
                ("usa", "ALL-USA sweep - one query per state + DC "
                        "(51 Places requests, billed)")):
            tk.Radiobutton(srow, text=label, value=value,
                           variable=self.dscope_var, bg=PANEL, fg=TEXT,
                           activebackground=PANEL, activeforeground=TEXT,
                           selectcolor=FIELD, font=(FONT, 9), relief="flat",
                           bd=0, highlightthickness=0).pack(side="left",
                                                            padx=(6, 14))

        brow = tk.Frame(top, bg=PANEL)
        brow.pack(fill="x", padx=12, pady=(0, 10))
        self.discover_btn = make_btn(brow, "Run Discovery", self.run_discover,
                                     kind="primary")
        self.discover_btn.pack(side="left")
        self.discover_status = tk.Label(brow, text="", bg=PANEL, fg=DIM,
                                        font=(FONT, 8))
        self.discover_status.pack(side="left", padx=12)

        lp = self._panel(f, "Activity",
                         "progress · blocked sites go to manual review - "
                         "never bypassed")
        lp.pack(fill="both", expand=True, pady=(10, 0))
        self.discover_log = self._make_log(lp)
        self.discover_log.pack(fill="both", expand=True, padx=12, pady=(2, 12))

    def run_discover(self):
        if _IMPORT_ERR:
            messagebox.showerror(
                "Missing components",
                "Scraping components failed to load:\n\n"
                + _IMPORT_ERR[-900:]
                + "\n\nDetails saved to %LOCALAPPDATA%\\SignalScout\\crash.log")
            return
        if self._busy:
            messagebox.showinfo("Busy", "Another job is already running.")
            return
        query = self.dq_var.get().strip()
        key = self.dkey_var.get().strip()
        if not query:
            messagebox.showinfo("Missing query",
                                "Enter a market query such as: "
                                "Total Wireless retailer in Houston TX")
            return
        sweep = self.dscope_var.get() == "usa"
        self._busy = True
        self._busy_start(self.discover_btn, self.discover_status,
                         "Discovering…")
        pages = self.dpages_var.get() or 1
        enrich = bool(self.denrich_var.get())
        if sweep:
            product = query.split(" in ")[0].strip() or "Total Wireless retailer"
            queries = sweep_queries(product)
            self.log(self.discover_log,
                     f"ALL-USA sweep: {len(queries)} state queries "
                     f"('{product} in <state>')")
        else:
            queries = [query]
            self.log(self.discover_log, "Discovery started: " + query)

        def work():
            try:
                collected = []
                crawler = PublicSiteCrawler(delay_seconds=2.5)
                for q_index, one_query in enumerate(queries, start=1):
                    found = search_places(one_query, key, pages)
                    collected.extend(found)
                    self._q.put((self._log_line,
                                 (self.discover_log,
                                  f"[{q_index}/{len(queries)}] {one_query} -> "
                                  f"{len(found)} businesses")))
                    if enrich:
                        for lead in found:
                            if lead.website:
                                crawler.enrich(lead.website, lead)
                    self._q.put((self._sweep_progress,
                                 (q_index, len(queries), len(collected))))
                    if q_index < len(queries):
                        time.sleep(1.5)     # polite pause between markets
                self._q.put((self._discover_done, collected))
            except Exception as exc:
                self._q.put((self._job_error,
                             (self.discover_log, self.discover_btn,
                              self.discover_status, exc)))

        threading.Thread(target=work, daemon=True).start()

    def _sweep_progress(self, payload):
        done, total, collected = payload
        self.discover_status.config(
            text=f"Sweep {done}/{total} markets · {collected} businesses",
            fg=WARN)

    def _log_line(self, payload):
        widget, message = payload
        self.log(widget, message)

    def _discover_done(self, payload):
        leads = payload
        self._busy = False
        self._busy_end(self.discover_btn, self.discover_status,
                       f"Done - {len(leads)} businesses collected")
        self.log(self.discover_log, f"Collected {len(leads)} records",
                 color=OK)
        self._absorb_leads(leads)

    def _job_error(self, payload):
        widget, button, status, exc = payload
        self._busy = False
        self._busy_end(button, status, f"Failed - {exc}", good=False)
        self.log(widget, f"ERROR: {exc}", color=ERR)

    def _absorb_leads(self, leads):
        self._leads = dedupe(self._leads + list(leads))
        self.hdr_count.config(text=f"{len(self._leads)} leads")
        if self.current_tab == "results":
            self._refresh_results()

    # ------------------------------------------------------------------
    # web scraper tab
    # ------------------------------------------------------------------
    def _build_scraper_tab(self):
        f = self._tab("scraper")
        top = self._panel(f, "Public website scraper",
                          "MechanicalSoup + BeautifulSoup · optional "
                          "browser-fingerprint mode for passively protected "
                          "(Cloudflare-fronted) sites · robots.txt respected · "
                          "challenges never bypassed")
        top.pack(fill="x")
        grid = tk.Frame(top, bg=PANEL)
        grid.pack(fill="x", padx=12, pady=(4, 12))
        grid.columnconfigure(0, weight=1)

        tk.Label(grid, text="Business websites (one per line)", bg=PANEL,
                 fg=DIM, font=(FONT, 9)).grid(row=0, column=0, sticky="w")
        self.scr_urls = tk.Text(grid, bg=FIELD, fg=TEXT, relief="flat",
                                font=(MONO, 9), height=6, wrap="none",
                                insertbackground=TEXT, highlightthickness=1,
                                highlightbackground=BORDER, bd=0)
        self.scr_urls.grid(row=1, column=0, sticky="we", pady=(2, 6))

        orow = tk.Frame(grid, bg=PANEL)
        orow.grid(row=2, column=0, sticky="w", pady=3)
        self.scr_impersonate = tk.BooleanVar(value=False)
        tk.Checkbutton(orow, text="Browser-fingerprint mode (curl_cffi "
                                  "Chrome TLS) for sites that 403 plain "
                                  "clients", variable=self.scr_impersonate,
                       bg=PANEL, fg=TEXT, activebackground=PANEL,
                       activeforeground=TEXT, selectcolor=FIELD,
                       font=(FONT, 9), relief="flat", bd=0,
                       highlightthickness=0).pack(side="left")

        brow = tk.Frame(top, bg=PANEL)
        brow.pack(fill="x", padx=12, pady=(0, 10))
        self.scr_btn = make_btn(brow, "Scrape Websites", self.run_scraper,
                                kind="primary")
        self.scr_btn.pack(side="left")
        self.scr_status = tk.Label(brow, text="", bg=PANEL, fg=DIM,
                                   font=(FONT, 8))
        self.scr_status.pack(side="left", padx=12)

        loc = self._panel(f, "Dealer locator search",
                          "Public store-locator forms · plain-HTML locators "
                          "via MechanicalSoup, JavaScript locators via CDP "
                          "trusted input in your own browser")
        loc.pack(fill="x", pady=(10, 0))
        lgrid = tk.Frame(loc, bg=PANEL)
        lgrid.pack(fill="x", padx=12, pady=(4, 10))
        lgrid.columnconfigure(1, weight=1)
        tk.Label(lgrid, text="Locator URL", bg=PANEL, fg=DIM,
                 font=(FONT, 9)).grid(row=0, column=0, sticky="w", pady=2)
        self.loc_url_var = tk.StringVar()
        tk.Entry(lgrid, textvariable=self.loc_url_var, bg=FIELD, fg=TEXT,
                 relief="flat", insertbackground=TEXT, font=(FONT, 10),
                 highlightbackground=BORDER, highlightthickness=1
                 ).grid(row=0, column=1, sticky="we", pady=2, ipady=4)
        tk.Label(lgrid, text="Search text", bg=PANEL, fg=DIM,
                 font=(FONT, 9)).grid(row=1, column=0, sticky="w", pady=2)
        self.loc_query_var = tk.StringVar(value="Total Wireless")
        tk.Entry(lgrid, textvariable=self.loc_query_var, bg=FIELD, fg=TEXT,
                 relief="flat", insertbackground=TEXT, font=(FONT, 10),
                 highlightbackground=BORDER, highlightthickness=1
                 ).grid(row=1, column=1, sticky="we", pady=2, ipady=4)
        tk.Label(lgrid, text="Mode", bg=PANEL, fg=DIM,
                 font=(FONT, 9)).grid(row=2, column=0, sticky="w", pady=2)
        mrow = tk.Frame(lgrid, bg=PANEL)
        mrow.grid(row=2, column=1, sticky="w", pady=2)
        self.loc_mode_var = tk.StringVar(value="mechanical")
        for value, label in (("mechanical", "MechanicalSoup (HTML forms)"),
                             ("cdp", "CDP trusted input (your browser)")):
            tk.Radiobutton(mrow, text=label, value=value,
                           variable=self.loc_mode_var, bg=PANEL, fg=TEXT,
                           activebackground=PANEL, activeforeground=TEXT,
                           selectcolor=FIELD, font=(FONT, 9), relief="flat",
                           bd=0, highlightthickness=0).pack(side="left",
                                                            padx=(0, 14))
        lrow = tk.Frame(loc, bg=PANEL)
        lrow.pack(fill="x", padx=12, pady=(0, 10))
        self.loc_btn = make_btn(lrow, "Search Locator", self.run_locator,
                                kind="primary")
        self.loc_btn.pack(side="left")
        self.loc_status = tk.Label(lrow, text="", bg=PANEL, fg=DIM,
                                   font=(FONT, 8))
        self.loc_status.pack(side="left", padx=12)

        lp = self._panel(f, "Activity", "per-page progress and statuses")
        lp.pack(fill="both", expand=True, pady=(10, 0))
        self.scraper_log = self._make_log(lp)
        self.scraper_log.pack(fill="both", expand=True, padx=12,
                              pady=(2, 12))

    def run_scraper(self):
        if _IMPORT_ERR:
            messagebox.showerror(
                "Missing components",
                "Scraping components failed to load:\n\n"
                + _IMPORT_ERR[-900:]
                + "\n\nDetails saved to %LOCALAPPDATA%\\SignalScout\\crash.log")
            return
        if self._busy:
            messagebox.showinfo("Busy", "Another job is already running.")
            return
        raw = self.scr_urls.get("1.0", "end")
        urls = [line.strip() for line in raw.splitlines()
                if line.strip().startswith(("http://", "https://"))]
        if not urls:
            messagebox.showinfo("Nothing to scrape",
                                "Paste one business website per line.")
            return
        self._busy = True
        self._busy_start(self.scr_btn, self.scr_status, "Scraping…")
        impersonate = bool(self.scr_impersonate.get())

        def work():
            try:
                crawler = PublicSiteCrawler(delay_seconds=2.5,
                                            impersonate=impersonate)
                if impersonate and not crawler.impersonate:
                    self._q.put((self._log_line,
                                 (self.scraper_log,
                                  "curl_cffi not available - falling back to "
                                  "plain MechanicalSoup mode", ERR)))
                leads = []
                for index, url in enumerate(urls, start=1):
                    self._q.put((self._log_line,
                                 (self.scraper_log,
                                  f"[{index}/{len(urls)}] {url}")))
                    leads.append(crawler.enrich(url))
                self._q.put((self._absorb_done,
                             (leads, self.scr_btn, self.scr_status,
                              self.scraper_log, "Scrape")))
            except Exception as exc:
                self._q.put((self._job_error,
                             (self.scraper_log, self.scr_btn,
                              self.scr_status, exc)))

        threading.Thread(target=work, daemon=True).start()

    def run_locator(self):
        if _IMPORT_ERR:
            messagebox.showerror(
                "Missing components",
                "Scraping components failed to load:\n\n"
                + _IMPORT_ERR[-900:]
                + "\n\nDetails saved to %LOCALAPPDATA%\\SignalScout\\crash.log")
            return
        if self._busy:
            messagebox.showinfo("Busy", "Another job is already running.")
            return
        url = self.loc_url_var.get().strip()
        query = self.loc_query_var.get().strip()
        if not url.startswith(("http://", "https://")) or not query:
            messagebox.showinfo("Missing input",
                                "Enter the locator URL and the search text.")
            return
        mode = self.loc_mode_var.get()
        if mode == "cdp" and (self._browser is None
                              or self._browser_session is None):
            messagebox.showinfo(
                "Browser not started",
                "Open the LinkedIn tab and start the browser first "
                "(log in there if the site needs it).")
            return
        self._busy = True
        self._busy_start(self.loc_btn, self.loc_status, "Searching…")
        self.log(self.scraper_log, f"Locator {mode} mode: {url} ({query})")

        def work():
            try:
                if mode == "mechanical":
                    result = search_locator_mechanical(url, query)
                else:
                    result = search_locator_cdp(self._browser,
                                                self._browser_session,
                                                url, query)
                self._q.put((self._log_line,
                             (self.scraper_log,
                              f"Locator status: {result.status} "
                              f"{result.note}")))
                self._q.put((self._absorb_done,
                             (result.leads, self.loc_btn, self.loc_status,
                              self.scraper_log, "Locator")))
            except Exception as exc:
                self._q.put((self._job_error,
                             (self.scraper_log, self.loc_btn,
                              self.loc_status, exc)))

        threading.Thread(target=work, daemon=True).start()

    def _absorb_done(self, payload):
        leads, button, status, logw, label = payload
        self._busy = False
        self._busy_end(button, status, f"{label} done - {len(leads)} records")
        self.log(logw, f"Collected {len(leads)} records", color=OK)
        self._absorb_leads(leads)

    # ------------------------------------------------------------------
    # linkedin tab (CDP trusted input)
    # ------------------------------------------------------------------
    def _build_linkedin_tab(self):
        f = self._tab("linkedin")
        top = self._panel(f, "LinkedIn public company reader",
                          "Uses YOUR own logged-in browser over CDP trusted "
                          "input (isTrusted clicks, eased mouse paths, hard "
                          "rate limits 6-12s). Log in yourself in the "
                          "browser window; the tool never touches your "
                          "credentials. On authwall/checkpoint it STOPS.")
        top.pack(fill="x")
        brow = tk.Frame(top, bg=PANEL)
        brow.pack(fill="x", padx=12, pady=(4, 10))
        self.li_start_btn = make_btn(brow, "Start Browser", self.start_browser,
                                     kind="primary")
        self.li_start_btn.pack(side="left")
        self.li_stop_btn = make_btn(brow, "Close Browser", self.stop_browser,
                                    kind="danger")
        self.li_stop_btn.pack(side="left", padx=(10, 0))
        self.li_status = tk.Label(brow, text="Browser not started",
                                  bg=PANEL, fg=DIM, font=(FONT, 8))
        self.li_status.pack(side="left", padx=12)

        mid = self._panel(f, "Find companies",
                          "Nationwide by default (LinkedIn search has no "
                          "geo limit) · two routes: your logged-in LinkedIn "
                          "search, or public search engines without login")
        mid.pack(fill="x", pady=(10, 0))
        mgrid = tk.Frame(mid, bg=PANEL)
        mgrid.pack(fill="x", padx=12, pady=(4, 10))
        mgrid.columnconfigure(1, weight=1)
        tk.Label(mgrid, text="Keywords", bg=PANEL, fg=DIM,
                 font=(FONT, 9)).grid(row=0, column=0, sticky="w", pady=2)
        self.li_kw_var = tk.StringVar(
            value="Total Wireless dealer")
        tk.Entry(mgrid, textvariable=self.li_kw_var, bg=FIELD, fg=TEXT,
                 relief="flat", insertbackground=TEXT, font=(FONT, 10),
                 highlightbackground=BORDER, highlightthickness=1
                 ).grid(row=0, column=1, sticky="we", pady=2, ipady=4)
        tk.Label(mgrid, text="Max results", bg=PANEL, fg=DIM,
                 font=(FONT, 9)).grid(row=1, column=0, sticky="w", pady=2)
        self.li_max_var = tk.IntVar(value=10)
        tk.Spinbox(mgrid, from_=1, to=25, width=5,
                   textvariable=self.li_max_var, bg=FIELD, fg=TEXT,
                   relief="flat", insertbackground=TEXT,
                   buttonbackground=PANEL, font=(FONT, 9),
                   highlightbackground=BORDER, highlightthickness=1
                   ).grid(row=1, column=1, sticky="w", pady=2)
        krow = tk.Frame(mid, bg=PANEL)
        krow.pack(fill="x", padx=12, pady=(0, 10))
        self.li_find_btn = make_btn(krow, "Find via LinkedIn Search",
                                    self.run_find, kind="primary")
        self.li_find_btn.pack(side="left")
        self.li_web_btn = make_btn(krow, "Find via Search Engine "
                                           "(no login)",
                                   self.run_web_find, kind="ghost")
        self.li_web_btn.pack(side="left", padx=(10, 0))
        self.li_find_status = tk.Label(krow, text="", bg=PANEL, fg=DIM,
                                       font=(FONT, 8))
        self.li_find_status.pack(side="left", padx=12)

        low = self._panel(f, "Company URLs to read",
                          "One /company/ URL per line (found by search or "
                          "pasted manually)")
        low.pack(fill="x", pady=(10, 0))
        self.li_urls = tk.Text(low, bg=FIELD, fg=TEXT, relief="flat",
                               font=(MONO, 9), height=6, wrap="none",
                               insertbackground=TEXT, highlightthickness=1,
                               highlightbackground=BORDER, bd=0)
        self.li_urls.pack(fill="x", padx=12, pady=(4, 8))
        lrow = tk.Frame(low, bg=PANEL)
        lrow.pack(fill="x", padx=12, pady=(0, 10))
        self.li_scrape_btn = make_btn(lrow, "Read Companies",
                                      self.run_linkedin, kind="primary")
        self.li_scrape_btn.pack(side="left")
        self.li_scrape_status = tk.Label(lrow, text="", bg=PANEL, fg=DIM,
                                         font=(FONT, 8))
        self.li_scrape_status.pack(side="left", padx=12)

        lp = self._panel(f, "Activity", "read progress · authwalled pages go "
                                        "to manual review")
        lp.pack(fill="both", expand=True, pady=(10, 0))
        self.li_log = self._make_log(lp)
        self.li_log.pack(fill="both", expand=True, padx=12, pady=(2, 12))

    def start_browser(self):
        if self._browser is not None:
            self.li_status.config(text="Browser already running", fg=OK)
            return
        from .cdp_browser import TrustedBrowser
        browser = TrustedBrowser()
        try:
            self.li_status.config(text="Starting browser…", fg=WARN)
            self.root.update_idletasks()
            browser.start()
            self._browser = browser
            self._browser_session = browser.open_tab()
            self.li_status.config(
                text="Browser running - log into websites yourself, then use "
                     "the actions below", fg=OK)
            self.log(self.li_log, "Browser started (CDP port "
                     f"{browser.port}). Log in to LinkedIn in that window.")
        except Exception as exc:
            self.li_status.config(text=f"Failed - {exc}", fg=ERR)
            self.log(self.li_log, f"Browser start failed: {exc}", color=ERR)

    def stop_browser(self):
        if self._browser is None:
            return
        try:
            self._browser.quit()
        finally:
            self._browser = None
            self._browser_session = None
            self.li_status.config(text="Browser closed", fg=DIM)
            self.log(self.li_log, "Browser closed.")

    def run_find(self):
        if self._browser is None or self._browser_session is None:
            messagebox.showinfo("Browser not started",
                                "Start the browser first.")
            return
        keywords = self.li_kw_var.get().strip()
        if not keywords:
            messagebox.showinfo("Missing keywords",
                                "Enter search keywords such as: "
                                "Total Wireless dealer Houston")
            return
        self._busy = True
        self._busy_start(self.li_find_btn, self.li_find_status, "Searching…")

        def work():
            try:
                urls = find_company_urls(self._browser,
                                         self._browser_session, keywords,
                                         self.li_max_var.get() or 10)
                self._q.put((self._find_done, (urls, keywords)))
            except Exception as exc:
                self._q.put((self._job_error,
                             (self.li_log, self.li_find_btn,
                              self.li_find_status, exc)))

        threading.Thread(target=work, daemon=True).start()

    def run_web_find(self):
        """LinkedIn Org-API alternative: public search engines
        (DuckDuckGo HTML / Bing) for site:linkedin.com/company pages -
        no LinkedIn session involved at all."""
        if _IMPORT_ERR:
            messagebox.showerror(
                "Missing components",
                "Scraping components failed to load:\n\n"
                + _IMPORT_ERR[-900:]
                + "\n\nDetails saved to %LOCALAPPDATA%\\SignalScout\\crash.log")
            return
        if self._busy:
            messagebox.showinfo("Busy", "Another job is already running.")
            return
        keywords = self.li_kw_var.get().strip()
        if not keywords:
            messagebox.showinfo("Missing keywords",
                                "Enter search keywords such as: "
                                "Total Wireless dealer")
            return
        self._busy = True
        self._busy_start(self.li_web_btn, self.li_find_status,
                         "Searching the open web…")
        self.log(self.li_log, "Search-engine discovery: "
                 f"site:linkedin.com/company {keywords}")

        def work():
            try:
                urls, status = find_company_urls_via_search(
                    keywords, limit=int(self.li_max_var.get() or 15))
                self._q.put((self._web_find_done, (urls, status, keywords)))
            except Exception as exc:
                self._q.put((self._job_error,
                             (self.li_log, self.li_web_btn,
                              self.li_find_status, exc)))

        threading.Thread(target=work, daemon=True).start()

    def _web_find_done(self, payload):
        urls, status, _keywords = payload
        self._busy = False
        good = status.startswith("ok")
        self._busy_end(self.li_web_btn, self.li_find_status,
                       f"{len(urls)} companies ({status})", good=good)
        self.log(self.li_log, f"Search engines returned {len(urls)} "
                 f"company pages [{status}]",
                 color=(OK if good else ERR))
        if urls:
            self.li_urls.delete("1.0", "end")
            self.li_urls.insert("1.0", "\n".join(urls))

    def _find_done(self, payload):
        urls, keywords = payload
        self._busy = False
        self._busy_end(self.li_find_btn, self.li_find_status,
                       f"Found {len(urls)} company pages")
        self.log(self.li_log, f"Search '{keywords}' found {len(urls)} pages",
                 color=OK)
        if urls:
            self.li_urls.delete("1.0", "end")
            self.li_urls.insert("1.0", "\n".join(urls))

    def run_linkedin(self):
        if self._browser is None or self._browser_session is None:
            messagebox.showinfo("Browser not started",
                                "Start the browser first.")
            return
        raw = self.li_urls.get("1.0", "end")
        urls = [line.strip() for line in raw.splitlines()
                if "/company/" in line]
        if not urls:
            messagebox.showinfo("Nothing to read",
                                "No /company/ URLs found in the list.")
            return
        self._busy = True
        self._busy_start(self.li_scrape_btn, self.li_scrape_status,
                         "Reading pages…")

        def progress(index, total, message):
            if total:
                self._q.put((self._log_line,
                             (self.li_log, f"[{index}/{total}] {message}")))
            else:
                self._q.put((self._log_line, (self.li_log, message)))

        def work():
            try:
                leads = scrape_companies(self._browser,
                                         self._browser_session, urls,
                                         progress=progress)
                self._q.put((self._absorb_done,
                             (leads, self.li_scrape_btn,
                              self.li_scrape_status, self.li_log,
                              "LinkedIn")))
            except Exception as exc:
                self._q.put((self._job_error,
                             (self.li_log, self.li_scrape_btn,
                              self.li_scrape_status, exc)))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------
    # results tab
    # ------------------------------------------------------------------
    def _build_results_tab(self):
        f = self._tab("results")
        top = self._panel(f, "Collected leads",
                          "Every record keeps its source URLs and evidence "
                          "notes · incomplete records also go to "
                          "manual-review.csv")
        top.pack(fill="x")
        grid = tk.Frame(top, bg=PANEL)
        grid.pack(fill="both", expand=True, padx=12, pady=(4, 10))
        self.res_list = tk.Listbox(grid, bg=FIELD, fg=TEXT, relief="flat",
                                   font=(MONO, 9), highlightthickness=1,
                                   highlightbackground=BORDER, bd=0,
                                   activestyle="none")
        self.res_list.pack(side="left", fill="both", expand=True)
        scroll = tk.Scrollbar(grid, command=self.res_list.yview)
        scroll.pack(side="left", fill="y")
        self.res_list.configure(yscrollcommand=scroll.set)
        self.res_list.bind("<<ListboxSelect>>", self._result_selected)
        self.res_detail = tk.Label(top, text="", bg=PANEL, fg=DIM,
                                   font=(FONT, 8), wraplength=800,
                                   justify="left", anchor="w")
        self.res_detail.pack(fill="x", padx=12, pady=(0, 8))
        brow = tk.Frame(top, bg=PANEL)
        brow.pack(fill="x", padx=12, pady=(0, 10))
        make_btn(brow, "Export Leads Excel (.xlsx)", self.export_leads_xlsx,
                 kind="primary").pack(side="left")
        make_btn(brow, "Export Leads CSV", self.export_leads,
                 kind="ghost").pack(side="left", padx=(10, 0))
        make_btn(brow, "Export Review Excel", self.export_review_xlsx,
                 kind="warn").pack(side="left", padx=(10, 0))
        make_btn(brow, "Clear All", self.clear_leads,
                 kind="danger").pack(side="right")

    def _refresh_results(self):
        self.res_list.delete(0, "end")
        for lead in self._leads:
            owner = lead.owner_name or "-"
            phone = lead.phone or "-"
            self.res_list.insert(
                "end", f"{lead.business_name[:38]:<38}  {owner[:22]:<22}  "
                       f"{phone:<16} {lead.status}")
        self.hdr_count.config(text=f"{len(self._leads)} leads")

    def _result_selected(self, _e=None):
        sel = self.res_list.curselection()
        if not sel:
            return
        lead = self._leads[sel[0]]
        sources = " | ".join(lead.source_urls[:3])
        evidence = " | ".join(lead.evidence[:2])
        self.res_detail.config(
            text=(f"{lead.business_name} · {lead.owner_name or 'owner: -'} · "
                  f"{lead.phone or '-'} · {lead.email or '-'} · "
                  f"{lead.address or '-'} · {lead.website or '-'}   "
                  f"[{sources}] {evidence}"))

    def export_leads(self):
        if not self._leads:
            messagebox.showinfo("Nothing to export", "No leads collected yet.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile="signal-scout-leads.csv",
            filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        write_csv(path, self._leads)
        self.res_detail.config(text=f"Saved {path}")

    def export_leads_xlsx(self):
        if not self._leads:
            messagebox.showinfo("Nothing to export", "No leads collected yet.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx", initialfile="signal-scout-leads.xlsx",
            filetypes=[("Excel workbooks", "*.xlsx")])
        if not path:
            return
        write_xlsx(path, self._leads)
        self.res_detail.config(
            text=f"Saved {path} - sheet Leads ({len(self._leads)} rows) "
                 f"+ sheet Manual Review")

    def export_review_xlsx(self):
        review = [lead for lead in self._leads if lead.status != "ok"]
        if not review:
            messagebox.showinfo("Nothing to export",
                                "No manual-review records right now.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx", initialfile="manual-review.xlsx",
            filetypes=[("Excel workbooks", "*.xlsx")])
        if not path:
            return
        write_xlsx(path, review)
        self.res_detail.config(text=f"Saved {path}")

    def export_review(self):
        review = [lead for lead in self._leads if lead.status != "ok"]
        if not review:
            messagebox.showinfo("Nothing to export",
                                "No manual-review records right now.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile="manual-review.csv",
            filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        write_csv(path, review)
        self.res_detail.config(text=f"Saved {path}")

    def clear_leads(self):
        if messagebox.askyesno("Clear all",
                               "Remove all collected leads from this "
                               "session?"):
            self._leads = []
            self._refresh_results()

    # ------------------------------------------------------------------
    # settings tab
    # ------------------------------------------------------------------
    def _build_settings_tab(self):
        f = self._tab("settings")
        top = self._panel(f, "Scout settings",
                          "Saved to ~/.signalscout/settings.json - English "
                          "UI only, polite scraping defaults")
        top.pack(fill="x")
        grid = tk.Frame(top, bg=PANEL)
        grid.pack(fill="x", padx=12, pady=(4, 12))
        grid.columnconfigure(1, weight=1)

        tk.Label(grid, text="User-Agent", bg=PANEL, fg=DIM,
                 font=(FONT, 9)).grid(row=0, column=0, sticky="w", pady=3)
        self.st_ua_var = tk.StringVar(value=str(self.settings.get(
            "user_agent", "SignalScout/0.2 (+contact: operator)")))
        tk.Entry(grid, textvariable=self.st_ua_var, bg=FIELD, fg=TEXT,
                 relief="flat", insertbackground=TEXT, font=(FONT, 10),
                 highlightbackground=BORDER, highlightthickness=1
                 ).grid(row=0, column=1, sticky="we", pady=3, ipady=4)

        tk.Label(grid, text="Request delay (s)", bg=PANEL, fg=DIM,
                 font=(FONT, 9)).grid(row=1, column=0, sticky="w", pady=3)
        self.st_delay_var = tk.StringVar(
            value=str(self.settings.get("delay", "2.5")))
        tk.Entry(grid, textvariable=self.st_delay_var, bg=FIELD, fg=TEXT,
                 relief="flat", insertbackground=TEXT, font=(FONT, 10),
                 highlightbackground=BORDER, highlightthickness=1
                 ).grid(row=1, column=1, sticky="we", pady=3, ipady=4)

        tk.Label(grid, text="LinkedIn profile dir", bg=PANEL, fg=DIM,
                 font=(FONT, 9)).grid(row=2, column=0, sticky="w", pady=3)
        self.st_profile_var = tk.StringVar(
            value=str(self.settings.get("profile_dir", "")))
        tk.Entry(grid, textvariable=self.st_profile_var, bg=FIELD, fg=TEXT,
                 relief="flat", insertbackground=TEXT, font=(FONT, 10),
                 highlightbackground=BORDER, highlightthickness=1
                 ).grid(row=2, column=1, sticky="we", pady=3, ipady=4)

        brow = tk.Frame(top, bg=PANEL)
        brow.pack(fill="x", padx=12, pady=(0, 10))
        make_btn(brow, "Save Settings", self.save_settings_now,
                 kind="primary").pack(side="left")
        self.st_status = tk.Label(brow, text="", bg=PANEL, fg=DIM,
                                  font=(FONT, 8))
        self.st_status.pack(side="left", padx=12)

        about = self._panel(f, "About",
                            "Compliance-first prospecting - what this tool "
                            "will never do")
        about.pack(fill="both", expand=True, pady=(10, 0))
        self.about_log = self._make_log(about, height=8)
        self.about_log.pack(fill="both", expand=True, padx=12, pady=(2, 12))
        for line, tag in (
            ("- No CAPTCHA solving and no challenge/Cloudflare bypass", "err"),
            ("- No credential, cookie, or session handling - you log in yourself", "err"),
            ("- No inferred private emails, personal numbers, or outreach", "err"),
            ("- robots.txt respected · hard rate limits · 401/403/429 stops", "ok"),
            ("- LinkedIn: your own account, public pages, at your own risk", "err"),
        ):
            self.log(self.about_log, line, color=(ERR if tag == "err" else OK))

    def save_settings_now(self):
        self.settings["user_agent"] = self.st_ua_var.get().strip()
        self.settings["delay"] = self.st_delay_var.get().strip()
        self.settings["profile_dir"] = self.st_profile_var.get().strip()
        self.settings["places_api_key"] = self.dkey_var.get().strip()
        save_settings(self.settings)
        self.st_status.config(text="Settings saved", fg=OK)

    def on_close(self):
        if self._browser is not None:
            try:
                self._browser.quit()
            except Exception:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = ScoutApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
