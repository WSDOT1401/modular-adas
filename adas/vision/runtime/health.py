"""Runtime health: how hard the Pi works, for the stats screen.

Camera + inference is the heaviest load on the Pi (active cooling is mandatory
in a car). :class:`HealthMonitor` reads the Pi's CPU load (all cores and each
core, from /proc/stat), memory in use (/proc/meminfo) and SoC temperature
(thermal zone 0); off a Pi, or wherever a file is missing, a reading is None.

The scheduler adds its frame rate and the AI HAT's figures and writes the lot
to :data:`STATS_FILE` once a second (:func:`write_stats`), where
``tools/stats_window.py`` shows it on a monitor of its own: never on the
driver's display.

TODO: shed load (skip frames / downshift) before thermal throttling makes the
alert path unreliable.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

STATS_FILE = Path("/dev/shm/adas-stats.json")     # RAM, not the SD card

_STAT = Path("/proc/stat")
_MEMINFO = Path("/proc/meminfo")
_THERMAL = Path("/sys/class/thermal/thermal_zone0/temp")


@dataclass
class HealthSnapshot:
    cpu_load: Optional[float] = None      # 0.0-1.0, all cores, since the last snapshot
    cpu_cores: List[float] = field(default_factory=list)   # the same per core
    mem_used: Optional[float] = None      # 0.0-1.0
    mem_total_gb: Optional[float] = None
    soc_temp_c: Optional[float] = None

    def as_dict(self) -> dict:
        out: dict = {}
        if self.cpu_load is not None:
            out["cpu_load"] = round(self.cpu_load, 3)
        if self.cpu_cores:
            out["cpu_cores"] = [round(c, 3) for c in self.cpu_cores]
        if self.mem_used is not None:
            out["mem_used"] = round(self.mem_used, 3)
            out["mem_total_gb"] = self.mem_total_gb
        if self.soc_temp_c is not None:
            out["cpu_temp_c"] = round(self.soc_temp_c, 1)
        return out


class HealthMonitor:
    def __init__(self) -> None:
        self._prev = self._cpu_times()

    @staticmethod
    def _cpu_times() -> "Dict[str, Tuple[int, int]]":
        """{"cpu": (total, idle), "cpu0": ..., ...} in jiffies."""
        out = {}
        try:
            for line in _STAT.read_text().splitlines():
                if not line.startswith("cpu"):
                    break
                name, *vals = line.split()
                fields = [int(v) for v in vals]
                out[name] = (sum(fields), fields[3] + fields[4])       # idle + iowait
        except (OSError, ValueError, IndexError):
            return {}
        return out

    @staticmethod
    def _load(now: Tuple[int, int], prev: Optional[Tuple[int, int]]) -> Optional[float]:
        if prev is None or now[0] <= prev[0]:
            return None
        return max(0.0, min(1.0, 1.0 - (now[1] - prev[1]) / (now[0] - prev[0])))

    @staticmethod
    def _memory() -> "Tuple[Optional[float], Optional[float]]":
        try:
            info = {k: int(v.split()[0]) for k, v in
                    (line.split(":", 1) for line in _MEMINFO.read_text().splitlines() if ":" in line)}
            total, free = info["MemTotal"], info["MemAvailable"]
        except (OSError, ValueError, KeyError):
            return None, None
        return 1.0 - free / total, round(total / 1024 / 1024, 1)

    @staticmethod
    def _soc_temp() -> Optional[float]:
        try:
            return int(_THERMAL.read_text()) / 1000.0
        except (OSError, ValueError):
            return None

    def snapshot(self) -> HealthSnapshot:
        """CPU load since the previous call; memory and temperature now."""
        now = self._cpu_times()
        snap = HealthSnapshot()
        if "cpu" in now:
            snap.cpu_load = self._load(now["cpu"], self._prev.get("cpu"))
            cores = sorted((k for k in now if k != "cpu"), key=lambda k: int(k[3:]))
            loads = [self._load(now[k], self._prev.get(k)) for k in cores]
            snap.cpu_cores = [v for v in loads if v is not None]
        self._prev = now
        snap.mem_used, snap.mem_total_gb = self._memory()
        snap.soc_temp_c = self._soc_temp()
        return snap


def write_stats(stats: dict) -> None:
    """Replace STATS_FILE in one step (a reader never sees half a file)."""
    import time

    stats = dict(stats, time=time.time(), pid=os.getpid())
    try:
        tmp = STATS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(stats))
        os.replace(tmp, STATS_FILE)
    except OSError:
        pass        # no /dev/shm (not Linux): no stats screen, nothing else changes


def clear_stats() -> None:
    try:
        STATS_FILE.unlink()
    except OSError:
        pass
