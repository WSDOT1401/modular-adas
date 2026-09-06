"""Process runtime: frame scheduler, vehicle-state cache, UDP publisher, health.

The plumbing that hosts the ``lane``/``signs`` stages as a long-running Pi
process and pushes results to the cluster over ``127.0.0.1:9100``.
"""
