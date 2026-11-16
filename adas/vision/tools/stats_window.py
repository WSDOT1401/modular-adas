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

On the Pi, next to the ADAS display on the round screen:

    python3 tools/stats_window.py                 # full screen on HDMI-A-1
    python3 tools/stats_window.py --windowed      # a window instead
    python3 tools/stats_window.py --text          # in the terminal (ssh)

Peaks (watts, temperatures, the supply's high and low) run from when the
window opened; r resets them. q or Esc closes it. Plain Python with Tk, no packages: it doesn't need the
venv. The AI HAT's load is worked out from its frame rate: HailoRT 5.1.1
gives no reading from inside the Hailo-10H.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

STATS_FILE = Path("/dev/shm/adas-stats.json")     # runtime/health.py writes it
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
class StatsWindow:
    def __init__(self, root, fullscreen: bool) -> None:
        import tkinter as tk

        self.root = root
        root.title("ADAS stats")
        root.configure(bg=BG)
        if fullscreen:
            # HDMI-A-1 starts at 0,0 (the round screen is beside it). Full screen
            # only takes once the window is up: asked for before, it's ignored.
            root.geometry("+0+0")
            root.after(300, lambda: root.attributes("-fullscreen", True))
            root.config(cursor="none")
        self.c = tk.Canvas(root, bg=BG, highlightthickness=0)
        self.c.pack(fill="both", expand=True)
        for key in ("<Escape>", "q", "Q"):
            root.bind(key, lambda _e: root.destroy())
        for key in ("r", "R"):
            root.bind(key, lambda _e: (self.peaks.reset(), self.draw()))
        root.bind("<Configure>", lambda _e: self.draw())
        self.stats: "dict | None" = None
        self.power: "dict | None" = None
        self.soc: "float | None" = None
        self.peaks = Peaks()
        self.hat = deque([None] * HISTORY, maxlen=HISTORY)
        self.cpu = deque([None] * HISTORY, maxlen=HISTORY)
        self.tick()

    def tick(self) -> None:
        self.stats = read()
        self.power = power()
        self.soc = soc_temp()
        if self.soc is None and self.stats:
            self.soc = self.stats.get("cpu_temp_c")
        self.peaks.update(self.stats, self.power, self.soc)
        s = self.stats or {}
        self.hat.append(s.get("hat_load"))
        self.cpu.append(s.get("cpu_load"))
        self.draw()
        self.root.after(1000, self.tick)

    # -- drawing helpers (u = one design pixel at 1600x900) --
    def font(self, px: float, bold: bool = False):
        return (FONT, -max(8, round(px * self.u)), "bold" if bold else "normal")

    def text(self, x, y, s, px, colour=TEXT, anchor="nw", bold=False):
        self.c.create_text(x, y, text=s, fill=colour, font=self.font(px, bold), anchor=anchor)

    def bar(self, x, y, w, h, v, colour):
        self.c.create_rectangle(x, y, x + w, y + h, fill=TRACK, width=0)
        if v is not None:
            self.c.create_rectangle(x, y, x + w * max(0.0, min(v, 1.0)), y + h, fill=colour, width=0)

    def graph(self, x, y, w, h, history, colour):
        u = self.u
        self.c.create_rectangle(x, y, x + w, y + h, fill=BG, outline=TRACK, width=max(1, round(u)))
        for f in (0.25, 0.5, 0.75):
            gy = y + h * (1 - f)
            self.c.create_line(x, gy, x + w, gy, fill=FAINT, dash=(2, 4))
            self.text(x + 8 * u, gy - 2 * u, f"{f * 100:.0f}%", 13, FAINT, anchor="sw")
        step = w / (HISTORY - 1)
        run = []
        for i, v in enumerate(list(history) + [None]):
            if v is None:
                if len(run) >= 2:
                    pts = [c for px, py in run for c in (px, py)]
                    fill = pts + [run[-1][0], y + h, run[0][0], y + h]
                    self.c.create_polygon(*fill, fill=TRACK, outline="")
                    self.c.create_line(*pts, fill=colour, width=max(2, round(2.5 * u)))
                run = []
                continue
            run.append((x + i * step, y + h * (1 - max(0.0, min(v, 1.0)))))
        self.text(x + w - 8 * u, y + h + 6 * u, "last 2 minutes", 13, DIM, anchor="ne")

    def rows(self, x, y, w, rows):
        """label ... value, with an optional dim note (a peak) between them."""
        for label, value, colour, *note in rows:
            self.text(x, y, label, 22, DIM)
            if note and note[0]:
                self.text(x + w * 0.44, y + 4 * self.u, note[0], 18, DIM)
            self.text(x + w, y, value, 26, colour, anchor="ne")
            y += 48 * self.u
        return y

    # -- the screen --
    def draw(self) -> None:
        c = self.c
        c.delete("all")
        W, H = max(c.winfo_width(), 320), max(c.winfo_height(), 200)
        self.u = u = min(W / 1600, H / 900)
        s = self.stats
        m = 40 * u

        self.text(m, m * 0.8, "ADAS VISION", 26, TEXT, bold=True)
        status = ("vision service not running" if s is None else
                  f"{s.get('source', '?')}   ·   pid {s.get('pid', '?')}   ·   "
                  f"{s.get('fps', 0):.1f} frames/s")
        self.text(W - m, m * 0.8, status, 20, CAUTION if s is None else DIM, anchor="ne")

        top = m * 0.8 + 60 * u
        pw = (W - 3 * m) / 2
        ph = H - top - m
        s = s or {}
        on_hat = s.get("hat_load") is not None

        # AI HAT
        x, y = m, top
        c.create_rectangle(x, y, x + pw, y + ph, fill=PANEL, width=0)
        ix, iw = x + 32 * u, pw - 64 * u
        self.text(ix, y + 28 * u, "AI HAT+ 2", 22, DIM, bold=True)
        self.text(ix + iw, y + 30 * u, "Hailo-10H", 18, DIM, anchor="ne")
        load = s.get("hat_load")
        self.text(ix, y + 62 * u, pct(load) if on_hat else "--", 104, load_colour(load))
        self.bar(ix, y + 200 * u, iw, 14 * u, load, load_colour(load))
        if on_hat:
            ry = self.rows(ix, y + 240 * u, iw, [
                ("Frames", f"{s.get('hat_fps', 0):.1f} fps", TEXT),
                ("Most it can do", f"{s.get('hat_max_fps') or 0:.0f} fps", DIM),
                ("Time per frame", f"{s.get('hat_latency_ms') or 0:.0f} ms", TEXT),
                ("Chip temperature", f"{s.get('hat_temp_c') or 0:.0f} °C", temp_colour(s.get("hat_temp_c")),
                 f"peak {fmt(self.peaks.hat, '°C')}"),
            ])
        else:
            self.text(ix, y + 240 * u, "not in use" if self.stats else "no data", 24, DIM)
            ry = y + 240 * u + 4 * 48 * u
        self.graph(ix, ry + 12 * u, iw, y + ph - ry - 60 * u, self.hat, INFO)

        # Pi
        x = 2 * m + pw
        c.create_rectangle(x, y, x + pw, y + ph, fill=PANEL, width=0)
        ix = x + 32 * u
        self.text(ix, y + 28 * u, "RASPBERRY PI 5", 22, DIM, bold=True)
        self.text(ix + iw, y + 30 * u, "CPU, all cores", 18, DIM, anchor="ne")
        load = s.get("cpu_load")
        self.text(ix, y + 62 * u, pct(load), 104, load_colour(load))
        self.bar(ix, y + 200 * u, iw, 14 * u, load, load_colour(load))
        cores = s.get("cpu_cores", [])
        cy = y + 240 * u
        if cores:
            gap = 14 * u
            cw = (iw - gap * (len(cores) - 1)) / len(cores)
            for i, v in enumerate(cores):
                cx = ix + i * (cw + gap)
                self.text(cx, cy, f"core {i + 1}", 16, DIM)
                self.text(cx + cw, cy, pct(v), 16, TEXT, anchor="ne")
                self.bar(cx, cy + 26 * u, cw, 8 * u, v, load_colour(v))
        mem, total = s.get("mem_used"), s.get("mem_total_gb")
        pk = self.peaks
        ry = self.rows(ix, cy + 60 * u, iw, [
            ("Memory", f"{mem * total:.1f} of {total:.0f} GB" if mem is not None and total else "--", TEXT),
            ("SoC temperature", fmt(self.soc, "°C"), temp_colour(self.soc), f"peak {fmt(pk.soc, '°C')}"),
            ("Pi draws", watts_text(self.power), TEXT, f"peak {fmt(pk.watts, 'W', 1)}"),
            ("Supply in", *supply_text(self.power),
             f"high {fmt(pk.v_high, 'V', 2)}   low {fmt(pk.v_low, 'V', 2)}"),
            ("Under-voltage", *undervolt_text(self.power)),
        ])
        self.graph(ix, ry + 12 * u, iw, y + ph - ry - 60 * u, self.cpu, INFO)
        self.text(ix, y + ph - 34 * u, f"{pk.label()}  ·  r resets", 13, DIM)


def main() -> int:
    ap = argparse.ArgumentParser(description="AI HAT and Pi load, on a screen of its own")
    ap.add_argument("--windowed", action="store_true", help="a window instead of full screen")
    ap.add_argument("--text", action="store_true", help="print to the terminal instead (ssh)")
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
    import tkinter as tk

    root = tk.Tk()
    StatsWindow(root, fullscreen=not args.windowed)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
