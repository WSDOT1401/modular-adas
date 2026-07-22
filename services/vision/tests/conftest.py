"""Make the service packages importable by tests without installing them.

Adds services/vision/ to sys.path so `from lane.departure import ...` (and
`import config`) work when running `pytest` from anywhere. (w124_protocol must
be installed: `pip install -e libs/protocol/python`.)
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
