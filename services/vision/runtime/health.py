"""Runtime health: frame rate, drops, and Pi thermal headroom.

Camera + inference is the heaviest load on the Pi (active cooling is mandatory —
see apps/cluster/README.md). This watches achieved FPS, dropped frames and SoC
temperature so the scheduler can shed load (skip frames / downshift) before
thermal throttling makes the alert path unreliable.

TODO: implement (read SoC temp; track FPS; expose a health snapshot).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class HealthSnapshot:
    fps: float = 0.0
    dropped: int = 0
    soc_temp_c: Optional[float] = None


class HealthMonitor:
    def snapshot(self) -> HealthSnapshot:
        """Return the current health snapshot."""
        raise NotImplementedError("TODO: health monitor")
