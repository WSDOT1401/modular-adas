"""Make the flat module importable by tests without installing it.

Adds services/lane_departure/ to sys.path so `from departure import ...` works
when running `pytest` from anywhere. (w124_protocol must be installed:
`pip install -e libs/protocol/python`.)
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
