"""Latest-vehicle-state cache.

The vision logic wants recent vehicle context — chiefly speed — to gate
warnings (e.g. suppress lane-departure alerts below a threshold, or scale sign
relevance). This caches the most recent values seen on the shared UDP contract
so stages can read them without each re-parsing the wire.

TODO: implement (subscribe/observe speed etc.; expose a cheap getter).
"""
from __future__ import annotations

from typing import Optional


class VehicleStateCache:
    def __init__(self) -> None:
        self._speed_kmh: Optional[float] = None

    @property
    def speed_kmh(self) -> Optional[float]:
        return self._speed_kmh

    def update(self, **fields) -> None:
        """Update cached fields from a decoded state payload."""
        raise NotImplementedError("TODO: vehicle-state cache")
