"""UDP publisher for the vision service.

Thin seam over the shared ``w124_protocol.UdpPublisher`` (libs/protocol) so the
rest of the service imports its publisher from one place. Keep pushing over UDP
to 127.0.0.1:9100 — never write files (SD-card wear; see commit 4135abb).

Re-exported here so callers do ``from runtime.publisher import UdpPublisher``;
add batching/rate-limiting here later without touching the scheduler.
"""
from __future__ import annotations

from w124_protocol import UdpPublisher  # re-export

__all__ = ["UdpPublisher"]
