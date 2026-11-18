#!/usr/bin/env python3
"""Stats screen: how hard the AI HAT and the Pi work, on a monitor of its own.

The driver's display never shows these. While the vision service runs it
writes its figures to /dev/shm/adas-stats.json once a second
(runtime/health.py); this window draws them, full screen on whichever
monitor you name, with the last two minutes as a graph:

  AI HAT   load (its fps against the most it does), fps, time per frame,
           chip temperature
  Pi       CPU (all cores and each core), memory, SoC temperature, the vision
           service's frame rate, and its power: the 5 V coming in, the watts
           it draws, and whether the supply has sagged (under-voltage). Power
           is read here, not by the vision service, so it shows with no model
           running.
  Video    what the vision service sees, with its boxes, beside the figures
           (runtime/preview.py). The window asks for it, in the size it
           wants, so a Pi with no stats screen never makes it.
  GPS      fix, satellites and speed, in the header (adas/sensors/gps.py)

On another machine (a Mac beside the car), reading tools/stats_server.py on
the Pi over the network, so the Pi only drives the round screen:

    python3 tools/stats_window.py --pi 172.20.10.2 --windowed

On the Pi itself, next to the ADAS display on the round screen:

    python3 tools/stats_window.py                 # full screen beside the round screen
    python3 tools/stats_window.py --windowed      # a window instead
    python3 tools/stats_window.py --text          # in the terminal (ssh)

Peaks (watts, temperatures, the supply's high and low) run from when the
window opened; r resets them. q or Esc closes it. Plain Python with GTK 3
(python3-gi, part of the Raspberry Pi OS desktop; on a Mac
``brew install gtk+3 pygobject3`` and Homebrew's python3): it doesn't need
the venv.
GTK, not Tk, because a GTK window is a Wayland one: a Tk window goes through
XWayland, and the video drawn there held the driver's display up to ~10
frames a second (vision README, "Room for the display"). The AI HAT's load is
worked out from its frame rate: HailoRT 5.1.1 gives no reading from inside
the Hailo-10H.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque
from http.client import HTTPException
from pathlib import Path

STATS_FILE = Path("/dev/shm/adas-stats.json")     # runtime/health.py writes it
FRAME_FILE = Path("/dev/shm/adas-frame.ppm")      # runtime/preview.py writes it
WANT_FILE = Path("/dev/shm/adas-frame.want")      # ... at the size asked for here
GPS_FILE = Path("/dev/shm/adas-gps.json")         # adas/sensors/gps.py writes it
PORT = 8090                                        # tools/stats_server.py
FRAME_MS = 66                                      # look for a new frame ~15 times a second
STALE_S = 3.0
HISTORY = 120                                      # seconds on the graphs

# The ADAS display's colours (adas/display/qml/Theme.qml).
BG, PANEL, TRACK = "#050607", "#0A0D10", "#161B20"
TEXT, DIM, FAINT = "#F2F4F5", "#8B949C", "#2A3138"
INFO, CAUTION, WARNING, ACTIVE = "#7CC4FF", "#FFB020", "#FF4D3D", "#4FD08A"
FONT = "DejaVu Sans"


# ---- power ---------------------------------------------------------------------
# vcgencmd get_throttled bits. The Pi 5 wants 5.1 V; below about 4.8 V it
# flags under-voltage and slows itself down.
UNDERVOLT_NOW, UNDERVOLT_SEEN = 1 << 0, 1 << 16
LOW_V = 4.85


def parse_pmic(text: str) -> "tuple[float | None, float | None]":
    """``vcgencmd pmic_read_adc`` -> (input volts, watts). The watts are each
    rail's current times its voltage, summed: the Pi's own circuits only, so
    the screens and USB devices draw more on top."""
    amps, volts = {}, {}
    for name, kind, value in re.findall(r"(\S+)_([AV]) \w+\(\d+\)=([\d.]+)", text):
        (amps if kind == "A" else volts)[name] = float(value)
    watts = sum(a * volts[n] for n, a in amps.items() if n in volts) if amps else None
    return volts.get("EXT5V"), watts


def power() -> "dict | None":
    """Input volts, watts and the throttle flags; None off a Pi."""
    if not shutil.which("vcgencmd"):
        return None
    try:
        pmic = subprocess.run(["vcgencmd", "pmic_read_adc"], capture_output=True,
                              text=True, timeout=2).stdout
        thr = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True,
                             text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    volts, watts = parse_pmic(pmic)
    m = re.search(r"0x([0-9a-fA-F]+)", thr)
    return {"volts": volts, "watts": watts, "flags": int(m.group(1), 16) if m else 0}


_THERMAL = Path("/sys/class/thermal/thermal_zone0/temp")


def soc_temp() -> "float | None":
    """The SoC temperature, read here too so it shows with no model running."""
    try:
        return int(_THERMAL.read_text()) / 1000.0
    except (OSError, ValueError):
        return None


def supply_text(p: "dict | None") -> "tuple[str, str]":
    """The supply voltage and its colour: amber under LOW_V."""
    if p is None or p.get("volts") is None:
        return "--", DIM
    v = p["volts"]
    return f"{v:.2f} V", CAUTION if v < LOW_V else TEXT


def undervolt_text(p: "dict | None") -> "tuple[str, str]":
    """What the Pi itself says about its supply: red while it sags, amber once it has."""
    if p is None:
        return "--", DIM
    flags = p.get("flags") or 0
    if flags & UNDERVOLT_NOW:
        return "too low now", WARNING
    if flags & UNDERVOLT_SEEN:
        return "dipped since boot", CAUTION
    return "never", TEXT


def watts_text(p: "dict | None") -> str:
    return "--" if p is None or p.get("watts") is None else f"{p['watts']:.1f} W"


class Peaks:
    """The most (and, for the supply, the least) seen since the window opened
    or was last reset with r. The supply's low matters more than its high:
    a sag is what makes the Pi throttle."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.watts = self.soc = self.hat = self.v_high = self.v_low = None
        self.since = time.time()

    @staticmethod
    def _hi(old, new):
        return new if old is None or (new is not None and new > old) else old

    @staticmethod
    def _lo(old, new):
        return new if old is None or (new is not None and new < old) else old

    def update(self, stats: "dict | None", p: "dict | None", soc: "float | None") -> None:
        p, stats = p or {}, stats or {}
        self.watts = self._hi(self.watts, p.get("watts"))
        self.v_high = self._hi(self.v_high, p.get("volts"))
        self.v_low = self._lo(self.v_low, p.get("volts"))
        self.soc = self._hi(self.soc, soc)
        self.hat = self._hi(self.hat, stats.get("hat_temp_c"))

    def label(self) -> str:
        mins = int((time.time() - self.since) // 60)
        return f"peaks over {mins // 60} h {mins % 60:02d} min" if mins >= 60 else f"peaks over {mins} min"


def fmt(v, unit: str, digits: int = 0) -> str:
    return "--" if v is None else f"{v:.{digits}f} {unit}"


def read() -> "dict | None":
    try:
        stats = json.loads(STATS_FILE.read_text())
    except (OSError, ValueError):
        return None
    return stats if time.time() - stats.get("time", 0) < STALE_S else None


def gps() -> "dict | None":
    """The GPS fix, or None when gps.py isn't running or the module is quiet."""
    try:
        if time.time() - GPS_FILE.stat().st_mtime > STALE_S:
            return None
        return json.loads(GPS_FILE.read_text())
    except (OSError, ValueError):
        return None


def snapshot() -> dict:
    """Everything but the video, read on this machine: the Pi. Every age is
    judged here, against the Pi's clock, so a window on another machine
    (stats_server.py sends it this dict) needn't share the Pi's time."""
    return {"stats": read(), "power": power(), "soc": soc_temp(), "gps": gps()}


def gps_text(g: "dict | None") -> "tuple[str, str]":
    """The header's GPS line and its colour: amber until it has a fix."""
    if g is None:
        return "GPS --", DIM
    sats = f"{g.get('sats_used') or 0}/{g.get('sats_in_view') or 0} sats"
    if not g.get("fix"):
        return f"GPS no fix  ·  {sats}", CAUTION
    kmh = g.get("speed_kmh")
    return (f"GPS {g.get('mode', '')} fix  ·  {sats}  ·  "
            + ("--" if kmh is None else f"{kmh:.0f} km/h")), TEXT


class Remote:
    """The same figures and video from tools/stats_server.py on the Pi, fetched
    in threads of their own: a slow hotspot then delays a frame, never the
    window. The window takes whatever arrived last."""

    def __init__(self, host: str) -> None:
        name, _, port = host.partition(":")
        # IPv4 only: w124.local also resolves to an IPv6 link-local address,
        # and every request would sit out its timeout there first.
        self.base = f"http://{socket.gethostbyname(name)}:{port or PORT}"
        self.snap: dict = {}
        self.frame: "tuple[bytes, float] | None" = None   # JPEG, monotonic time it came
        self.size: "tuple[int, int] | None" = None        # set by the window
        for loop in (self._stats, self._frames):
            threading.Thread(target=loop, daemon=True).start()

    def _get(self, path: str) -> "tuple[int, bytes]":
        with urllib.request.urlopen(self.base + path, timeout=2) as r:
            return r.status, r.read()

    def _stats(self) -> None:
        while True:
            try:
                self.snap = json.loads(self._get("/stats")[1])
            except (OSError, ValueError, HTTPException):
                self.snap = {}                             # the Pi or its server is down
            time.sleep(1.0)

    def _frames(self) -> None:
        while True:
            t = time.monotonic()
            if self.size is not None:
                try:
                    status, body = self._get("/frame?w=%d&h=%d" % self.size)
                    if status == 200:
                        self.frame = (body, time.monotonic())
                except (OSError, HTTPException):
                    pass
            time.sleep(max(0.0, FRAME_MS / 1000 - (time.monotonic() - t)))


def load_colour(v) -> str:
    return CAUTION if v is not None and v >= 0.9 else INFO


def temp_colour(t) -> str:
    if t is None:
        return TEXT
    return WARNING if t >= 85 else CAUTION if t >= 80 else TEXT


def pct(v) -> str:
    return "--" if v is None else f"{v * 100:.0f}%"


# ---- terminal ------------------------------------------------------------------
def text_view(s: "dict | None") -> str:
    if s is None:
        return "vision service not running: no stats\n"

    def bar(v, n=24):
        full = round(max(0.0, min(v or 0.0, 1.0)) * n)
        return "█" * full + "░" * (n - full)

    out = []
    if s.get("hat_load") is not None:
        out += [f"AI HAT  {bar(s['hat_load'])} {pct(s['hat_load']):>4}   "
                f"{s.get('hat_fps', 0):.1f} fps of {s.get('hat_max_fps') or '?'}   "
                f"{s.get('hat_latency_ms') or 0:.0f} ms   {s.get('hat_temp_c') or 0:.0f} °C"]
    else:
        out += ["AI HAT  not in use"]
    out += [f"Pi CPU  {bar(s.get('cpu_load'))} {pct(s.get('cpu_load')):>4}   "
            + "  ".join(pct(c) for c in s.get("cpu_cores", [])) +
            f"   {s.get('cpu_temp_c') or 0:.0f} °C",
            f"Memory  {bar(s.get('mem_used'))} {pct(s.get('mem_used')):>4}   "
            f"vision {s.get('fps', 0):.1f} fps"]
    return "\n".join(out) + "\n"


def power_line(p: "dict | None", soc: "float | None", pk: Peaks) -> str:
    if p is None:
        return "Power   -- (no vcgencmd: not a Pi)\n"
    return (f"Power   in {supply_text(p)[0]} (high {fmt(pk.v_high, 'V', 2)}, low {fmt(pk.v_low, 'V', 2)}), "
            f"under-voltage {undervolt_text(p)[0]}\n"
            f"        Pi draws {watts_text(p)} (peak {fmt(pk.watts, 'W', 1)})   "
            f"SoC {fmt(soc, '°C')} (peak {fmt(pk.soc, '°C')})   {pk.label()}\n")


# ---- window --------------------------------------------------------------------
Gdk = GdkPixbuf = GLib = Gtk = Pango = PangoCairo = None     # GTK, loaded by StatsWindow


def rgb(colour: str) -> "tuple[float, float, float]":
    return tuple(int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5))


class StatsWindow:
    """The stats, drawn with cairo in a GTK 3 window (a Wayland one)."""

    def __init__(self, fullscreen: bool, remote: "Remote | None" = None) -> None:
        global Gdk, GdkPixbuf, GLib, Gtk, Pango, PangoCairo
        import gi  # type: ignore

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango, PangoCairo  # type: ignore

        self.remote = remote
        self.stats: "dict | None" = None
        self.power: "dict | None" = None
        self.soc: "float | None" = None
        self.gps: "dict | None" = None
        self.peaks = Peaks()
        self.hat = deque([None] * HISTORY, maxlen=HISTORY)
        self.cpu = deque([None] * HISTORY, maxlen=HISTORY)
        self.u = 1.0
        self.ph = 0.0
        self.cr = None
        self.fonts: dict = {}
        self.video_size: "tuple[int, int] | None" = None   # what we ask the vision service for
        self.video_at: "tuple[int, int, int, int] | None" = None   # x, y, w, h in the window
        self.frame_mtime = 0.0
        self.has_video = False
        self.pixbuf = None

        self.win = win = Gtk.Window(title="ADAS stats")
        self.area = Gtk.DrawingArea()
        self.area.connect("draw", self.on_draw)
        win.add(self.area)
        win.connect("destroy", Gtk.main_quit)
        win.connect("key-press-event", self.on_key)
        win.set_default_size(1600, 900)
        win.show_all()
        if fullscreen:
            win.get_window().set_cursor(Gdk.Cursor.new_from_name(win.get_display(), "none"))
            # Beside the round screen: on the monitor that isn't square.
            disp = win.get_display()
            shapes = [disp.get_monitor(i).get_geometry() for i in range(disp.get_n_monitors())]
            pick = next((i for i, g in enumerate(shapes) if g.width != g.height), 0)
            win.fullscreen_on_monitor(win.get_screen(), pick)
        self.tick()
        GLib.timeout_add(1000, self.tick)
        GLib.timeout_add(FRAME_MS, self.frame_tick)

    def on_key(self, _win, event) -> bool:
        key = Gdk.keyval_name(event.keyval)
        if key in ("Escape", "q", "Q"):
            Gtk.main_quit()
        elif key in ("r", "R"):
            self.peaks.reset()
            self.area.queue_draw()
        return True

    def tick(self) -> bool:
        snap = self.remote.snap if self.remote else snapshot()
        self.stats, self.power, self.soc, self.gps = (snap.get(k) for k in ("stats", "power", "soc", "gps"))
        if self.soc is None and self.stats:
            self.soc = self.stats.get("cpu_temp_c")
        self.peaks.update(self.stats, self.power, self.soc)
        s = self.stats or {}
        self.hat.append(s.get("hat_load"))
        self.cpu.append(s.get("cpu_load"))
        self.ask_for_video()
        self.has_video = self.frame_stamp() is not None
        self.area.queue_draw()
        return True

    # -- the video --
    def ask_for_video(self) -> None:
        """Tell the vision service we're watching, and at what size. Every second:
        a stale request means no one is, and it stops making frames."""
        if self.video_size is None:
            return
        if self.remote:
            self.remote.size = self.video_size                # sent with every frame request
            return
        try:
            WANT_FILE.write_text("%d %d\n" % self.video_size)
        except OSError:
            pass

    @staticmethod
    def fresh_frame() -> "float | None":
        try:
            mtime = FRAME_FILE.stat().st_mtime
        except OSError:
            return None
        return mtime if time.time() - mtime < STALE_S else None

    def frame_stamp(self) -> "float | None":
        """When the newest frame came, while it's fresh; None when there's none."""
        if not self.remote:
            return self.fresh_frame()
        got = self.remote.frame
        return got[1] if got and time.monotonic() - got[1] < STALE_S else None

    def load_frame(self):
        if not self.remote:
            return GdkPixbuf.Pixbuf.new_from_file(str(FRAME_FILE))
        loader = GdkPixbuf.PixbufLoader()
        loader.write(self.remote.frame[0])
        loader.close()
        return loader.get_pixbuf()

    def frame_tick(self) -> bool:
        mtime = self.frame_stamp()
        if (mtime is not None) != self.has_video:           # the feed came or went: relayout
            self.has_video = mtime is not None
            self.area.queue_draw()
        if mtime is not None and mtime != self.frame_mtime:
            self.frame_mtime = mtime
            try:
                self.pixbuf = self.load_frame()
            except GLib.Error:                                # replaced mid-read: take the next
                return True
            if self.video_at and self.has_video:
                self.area.queue_draw_area(*self.video_at)     # only the video: the rest stands
        return True

    def paint_video(self) -> None:
        x, y, w, h = self.video_at
        cr = self.cr
        cr.set_source_rgb(0, 0, 0)
        cr.rectangle(x, y, w, h)
        cr.fill()
        if self.pixbuf is not None:
            pw, ph = self.pixbuf.get_width(), self.pixbuf.get_height()
            px, py = round(x + (w - pw) / 2), round(y + (h - ph) / 2)
            Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, px, py)
            cr.rectangle(px, py, min(pw, w), min(ph, h))
            cr.fill()

    # -- drawing helpers (u = one design pixel at 1600x900) --
    def text(self, x, y, s, px, colour=TEXT, anchor="nw", bold=False):
        size = max(8, round(px * self.u))
        font = self.fonts.get((size, bold))
        if font is None:
            font = self.fonts[(size, bold)] = Pango.FontDescription(FONT + (" Bold" if bold else ""))
            font.set_absolute_size(size * Pango.SCALE)
        layout = PangoCairo.create_layout(self.cr)
        layout.set_font_description(font)
        layout.set_text(s, -1)
        _ink, box = layout.get_pixel_extents()
        if "e" in anchor:
            x -= box.width
        if "s" in anchor:
            y -= box.height
        self.cr.set_source_rgb(*rgb(colour))
        self.cr.move_to(x, y)
        PangoCairo.show_layout(self.cr, layout)
        return box.width

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, width=1.0):
        cr = self.cr
        cr.rectangle(x0, y0, x1 - x0, y1 - y0)
        if fill:
            cr.set_source_rgb(*rgb(fill))
            cr.fill_preserve()
        if outline:
            cr.set_source_rgb(*rgb(outline))
            cr.set_line_width(width)
            cr.stroke_preserve()
        cr.new_path()

    def line(self, pts, colour, width=1.0, dash=None):
        cr = self.cr
        cr.move_to(*pts[0])
        for p in pts[1:]:
            cr.line_to(*p)
        cr.set_source_rgb(*rgb(colour))
        cr.set_line_width(width)
        cr.set_dash(dash or [])
        cr.stroke()
        cr.set_dash([])

    def bar(self, x, y, w, h, v, colour):
        self.rect(x, y, x + w, y + h, fill=TRACK)
        if v is not None:
            self.rect(x, y, x + w * max(0.0, min(v, 1.0)), y + h, fill=colour)

    def graph(self, x, y, w, h, history, colour):
        u, cr = self.u, self.cr
        self.rect(x, y, x + w, y + h, fill=BG, outline=TRACK, width=max(1, round(u)))
        for f in (0.25, 0.5, 0.75):
            gy = y + h * (1 - f)
            self.line([(x, gy), (x + w, gy)], FAINT, 1, dash=[2, 4])
            self.text(x + 8 * u, gy - 2 * u, f"{f * 100:.0f}%", 13, FAINT, anchor="sw")
        step = w / (HISTORY - 1)
        run = []
        for i, v in enumerate(list(history) + [None]):
            if v is None:
                if len(run) >= 2:
                    cr.move_to(*run[0])
                    for p in run[1:] + [(run[-1][0], y + h), (run[0][0], y + h)]:
                        cr.line_to(*p)
                    cr.close_path()
                    cr.set_source_rgb(*rgb(TRACK))
                    cr.fill()
                    self.line(run, colour, max(2, round(2.5 * u)))
                run = []
                continue
            run.append((x + i * step, y + h * (1 - max(0.0, min(v, 1.0)))))
        self.text(x + w - 8 * u, y + h + 6 * u, "last 2 minutes", 13, DIM, anchor="ne")

    def rows(self, x, y, w, rows, line=48, sizes=(22, 18, 26)):
        """label ... value, with an optional dim note (a peak) between them."""
        lpx, npx, vpx = sizes
        for label, value, colour, *note in rows:
            self.text(x, y, label, lpx, DIM)
            if note and note[0]:
                self.text(x + w * 0.44, y + (lpx - npx) * self.u, note[0], npx, DIM)
            self.text(x + w, y, value, vpx, colour, anchor="ne")
            y += line * self.u
        return y

    # -- the screen --
    def on_draw(self, area, cr) -> bool:
        self.cr = cr
        x0, y0, x1, y1 = cr.clip_extents()
        v = self.video_at
        if (self.has_video and v and x0 >= v[0] and y0 >= v[1]
                and x1 <= v[0] + v[2] and y1 <= v[1] + v[3]):
            self.paint_video()                                # a new frame, nothing else
        else:
            self.draw(area.get_allocated_width(), area.get_allocated_height())
        return True

    def draw(self, W, H) -> None:
        W, H = max(W, 320), max(H, 200)
        self.rect(0, 0, W, H, fill=BG)
        self.u = u = min(W / 1600, H / 900)
        m = 40 * u
        top = self.header(W, m)
        s = self.stats or {}
        # Where the video goes; asked for before it comes, so that it can.
        lw = (W - 3 * m) * 0.62
        vh = min(lw * 9 / 16, H - top - m - 260 * u)
        self.video_size = (int(lw), int(vh))
        self.video_at = (int(m), int(top), int(lw) + 1, int(vh) + 1)
        if self.has_video:
            self.draw_with_video(W, H, m, top, s, lw, vh)
        else:
            self.draw_figures(W, H, m, top, s)

    def header(self, W, m) -> float:
        u, s = self.u, self.stats
        self.text(m, m * 0.8, "ADAS VISION", 26, TEXT, bold=True)
        status = (f"no answer from {self.remote.base}" if self.remote and not self.remote.snap else
                  "vision service not running" if s is None else
                  f"{s.get('source', '?')}   ·   pid {s.get('pid', '?')}   ·   "
                  f"{s.get('fps', 0):.1f} frames/s")
        w = self.text(W - m, m * 0.8, status, 20, CAUTION if s is None else DIM, anchor="ne")
        line, colour = gps_text(self.gps)
        self.text(W - m - w - 64 * u, m * 0.8, line, 20, colour, anchor="ne")
        return m * 0.8 + 60 * u

    def hat_rows(self, s):
        return [
            ("Frames", f"{s.get('hat_fps', 0):.1f} fps", TEXT),
            ("Most it can do", f"{s.get('hat_max_fps') or 0:.0f} fps", DIM),
            ("Time per frame", f"{s.get('hat_latency_ms') or 0:.0f} ms", TEXT),
            ("Chip temperature", f"{s.get('hat_temp_c') or 0:.0f} °C", temp_colour(s.get("hat_temp_c")),
             f"peak {fmt(self.peaks.hat, '°C')}"),
        ]

    def pi_rows(self, s):
        mem, total = s.get("mem_used"), s.get("mem_total_gb")
        pk = self.peaks
        return [
            ("Memory", f"{mem * total:.1f} of {total:.0f} GB" if mem is not None and total else "--", TEXT),
            ("SoC temperature", fmt(self.soc, "°C"), temp_colour(self.soc), f"peak {fmt(pk.soc, '°C')}"),
            ("Pi draws", watts_text(self.power), TEXT, f"peak {fmt(pk.watts, 'W', 1)}"),
            ("Supply in", *supply_text(self.power),
             f"high {fmt(pk.v_high, 'V', 2)}   low {fmt(pk.v_low, 'V', 2)}"),
            ("Under-voltage", *undervolt_text(self.power)),
        ]

    def cores(self, ix, cy, iw, s, px=16, bar=8) -> None:
        u, cores = self.u, s.get("cpu_cores", [])
        if not cores:
            return
        gap = 14 * u
        cw = (iw - gap * (len(cores) - 1)) / len(cores)
        for i, v in enumerate(cores):
            cx = ix + i * (cw + gap)
            self.text(cx, cy, f"core {i + 1}", px, DIM)
            self.text(cx + cw, cy, pct(v), px, TEXT, anchor="ne")
            self.bar(cx, cy + (px + 10) * u, cw, bar * u, v, load_colour(v))

    def panel_head(self, x, y, pw, title, aside, value, compact=False):
        """The panel, its title, the big percentage and its bar. Returns the inner x, width."""
        u = self.u
        self.rect(x, y, x + pw, y + self.ph, fill=PANEL)
        ix, iw = x + 32 * u, pw - 64 * u
        tpx, big, num_y, bar_y, bar_h = (18, 56, 50, 122, 10) if compact else (22, 104, 62, 200, 14)
        self.text(ix, y + 28 * u, title, tpx, DIM, bold=True)
        self.text(ix + iw, y + 30 * u, aside, tpx - 4, DIM, anchor="ne")
        self.text(ix, y + num_y * u, pct(value), big, load_colour(value))
        self.bar(ix, y + bar_y * u, iw, bar_h * u, value, load_colour(value))
        return ix, iw

    # The figures alone: two tall panels side by side, a graph in each.
    def draw_figures(self, W, H, m, top, s) -> None:
        u = self.u
        pw = (W - 3 * m) / 2
        self.ph = ph = H - top - m
        y = top

        ix, iw = self.panel_head(m, y, pw, "AI HAT+ 2", "Hailo-10H", s.get("hat_load"))
        if s.get("hat_load") is not None:
            ry = self.rows(ix, y + 240 * u, iw, self.hat_rows(s))
        else:
            self.text(ix, y + 240 * u, "not in use" if self.stats else "no data", 24, DIM)
            ry = y + 240 * u + 4 * 48 * u
        self.graph(ix, ry + 12 * u, iw, y + ph - ry - 60 * u, self.hat, INFO)

        ix, iw = self.panel_head(2 * m + pw, y, pw, "RASPBERRY PI 5", "CPU, all cores", s.get("cpu_load"))
        cy = y + 240 * u
        self.cores(ix, cy, iw, s)
        ry = self.rows(ix, cy + 60 * u, iw, self.pi_rows(s))
        self.graph(ix, ry + 12 * u, iw, y + ph - ry - 60 * u, self.cpu, INFO)
        self.text(ix, y + ph - 34 * u, f"{self.peaks.label()}  ·  r resets", 13, DIM)

    # With the video: it and the two graphs on the left, the figures stacked on the right.
    def draw_with_video(self, W, H, m, top, s, lw, vh) -> None:
        u = self.u
        self.paint_video()

        gy = top + vh + 40 * u
        gw = (lw - m) / 2
        gh = H - m - gy - 26 * u
        for i, (name, hist) in enumerate((("AI HAT load", self.hat), ("Pi CPU", self.cpu))):
            gx = m + i * (gw + m)
            self.text(gx, gy - 6 * u, name, 16, DIM, anchor="sw")
            self.graph(gx, gy, gw, gh, hist, INFO)

        x, pw = 2 * m + lw, W - 3 * m - lw
        avail = H - top - m - m * 0.5
        sizes, line = (17, 13, 20), 36

        self.ph = avail * 0.42
        ix, iw = self.panel_head(x, top, pw, "AI HAT+ 2", "Hailo-10H", s.get("hat_load"), compact=True)
        if s.get("hat_load") is not None:
            self.rows(ix, top + 150 * u, iw, self.hat_rows(s), line, sizes)
        else:
            self.text(ix, top + 150 * u, "not in use" if self.stats else "no data", 18, DIM)

        y = top + self.ph + m * 0.5
        self.ph = avail - self.ph
        ix, iw = self.panel_head(x, y, pw, "RASPBERRY PI 5", "CPU, all cores", s.get("cpu_load"),
                                 compact=True)
        self.cores(ix, y + 150 * u, iw, s, px=14, bar=6)
        self.rows(ix, y + 198 * u, iw, self.pi_rows(s), line, sizes)
        self.text(ix, y + self.ph - 30 * u, f"{self.peaks.label()}  ·  r resets", 12, DIM)


def main() -> int:
    ap = argparse.ArgumentParser(description="AI HAT and Pi load, on a screen of its own")
    ap.add_argument("--windowed", action="store_true", help="a window instead of full screen")
    ap.add_argument("--text", action="store_true", help="print to the terminal instead (ssh)")
    ap.add_argument("--all-cores", action="store_true",
                    help="don't keep off the display's cores (config.DISPLAY_CORES)")
    ap.add_argument("--pi", metavar="HOST[:PORT]",
                    help="run on another machine: read tools/stats_server.py on the Pi")
    args = ap.parse_args()
    if args.text:
        peaks = Peaks()
        try:
            while True:
                stats, p, soc = read(), power(), soc_temp()
                peaks.update(stats, p, soc)
                sys.stdout.write("\033[H\033[J" + text_view(stats) + power_line(p, soc, peaks)
                                 + "\nCtrl+C to quit\n")
                sys.stdout.flush()
                time.sleep(1.0)
        except KeyboardInterrupt:
            return 0
    # Off the display's cores too, below it in priority: drawing the video
    # here is real work (runtime/priority.py). Not on another machine.
    if not args.all_cores and not args.pi:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import config
        from runtime.priority import yield_to_display
        print(f"stats window: {yield_to_display(config.DISPLAY_CORES, config.VISION_NICE)}",
              flush=True)
    # Started over ssh, only DISPLAY may be set, and GTK would then take X11
    # (XWayland): find the desktop's Wayland socket instead.
    run = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
    if "WAYLAND_DISPLAY" not in os.environ and (run / "wayland-0").exists():
        os.environ.update(XDG_RUNTIME_DIR=str(run), WAYLAND_DISPLAY="wayland-0")
    StatsWindow(fullscreen=not args.windowed, remote=Remote(args.pi) if args.pi else None)
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
