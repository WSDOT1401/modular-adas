"""Leave the driver's display room to run.

The vision service takes whatever CPU it can get: the clip or camera frames,
resizing, the crops for M2, and the thread pools of OpenCV and PyTorch, which
start one thread per core. The display (adas/display, Qt) and the desktop that
draws it then wait their turn and stutter.

So the vision service, and the stats window that watches it, keep off the
cores in :data:`config.DISPLAY_CORES` and run at a lower priority
(:data:`config.VISION_NICE`): the display, the desktop compositor and X always
find a free core, and win any core they share with vision. Neither needs root.

Call it first thing, before any thread starts and before OpenCV, NumPy or
PyTorch are imported: new threads take the cores of the thread that starts
them, and the libraries size their thread pools when they load.
"""
from __future__ import annotations

import os
from typing import Iterable

# Thread pools that size themselves from the core count when they load
# (PyTorch, NumPy). OpenCV counts the cores this process may use by itself.
_POOLS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")


def yield_to_display(display_cores: Iterable[int], nice: int) -> str:
    """Move this process off ``display_cores`` and lower its priority by ``nice``.

    Returns what it did, for the log. Does nothing where it can't (Windows,
    macOS) or where it would leave no core (a machine with fewer cores).
    """
    done = []
    if hasattr(os, "sched_setaffinity"):
        have = os.sched_getaffinity(0)
        keep = have - set(display_cores)
        if keep and keep != have:
            os.sched_setaffinity(0, keep)
            for var in _POOLS:
                os.environ.setdefault(var, str(len(keep)))
            done.append(f"cores {','.join(map(str, sorted(keep)))}")
    if nice and hasattr(os, "nice"):
        try:
            done.append(f"nice {os.nice(nice)}")
        except OSError:
            pass
    return ", ".join(done) or "all cores, normal priority"

