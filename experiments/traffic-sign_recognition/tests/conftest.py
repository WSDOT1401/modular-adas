"""Make the experiment modules importable by tests without installing them.

Adds experiments/traffic-sign_recognition/ to sys.path so `import classes` and
`import prepare_gtsdb` work when running `pytest` from anywhere.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
