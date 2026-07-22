"""Frame acquisition backends.

``base.FrameSource`` is the abstraction the rest of the pipeline consumes; the
concrete backends (Picamera2 on the Pi, OpenCV file-replay off-Pi) live beside
it in this package.
"""
