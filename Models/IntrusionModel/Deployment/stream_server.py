"""MJPEG stream server so the dashboard can watch what the detector sees.

The browser cannot open the webcam at the same time as OpenCV -- on Windows the
device is effectively exclusive -- so the dashboard cannot use getUserMedia
while detection is running. Instead the detector, which already owns the
camera, republishes its annotated frames as MJPEG. That is also how a real CCTV
deployment behaves: the camera is a stream source and the dashboard is a viewer.

Serves:
    GET /stream   multipart/x-mixed-replace MJPEG, viewable in an <img>
    GET /snapshot single JPEG of the latest frame
    GET /healthz  plain-text ok

Only the most recent frame is kept. A slow or stalled viewer therefore skips
frames instead of applying backpressure to the detection loop.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2


BOUNDARY = "sflmsframe"


class FrameBuffer:
    """Single-slot buffer holding the latest encoded JPEG."""

    def __init__(self):
        self._condition = threading.Condition()
        self._jpeg = None
        self._sequence = 0
        self._closed = False

    def publish(self, frame, quality=80):
        encoded, buffer = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        )
        if not encoded:
            return
        with self._condition:
            self._jpeg = buffer.tobytes()
            self._sequence += 1
            self._condition.notify_all()

    def latest(self):
        with self._condition:
            return self._jpeg

    def wait_for_next(self, last_sequence, timeout=5.0):
        """Block until a frame newer than last_sequence exists."""
        with self._condition:
            self._condition.wait_for(
                lambda: self._sequence != last_sequence or self._closed,
                timeout=timeout,
            )
            if self._closed:
                return None, self._sequence
            return self._jpeg, self._sequence

    def close(self):
        with self._condition:
            self._closed = True
            self._condition.notify_all()


def build_handler(buffer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *args):
            pass  # keep the detector's stdout readable

        def _cors(self):
            # The dashboard is served from a different port, and an <img> tag
            # does not need CORS -- but fetch()/canvas use would, so allow it.
            self.send_header("Access-Control-Allow-Origin", "*")

        def do_GET(self):
            path = self.path.split("?")[0].rstrip("/") or "/"
            if path == "/healthz":
                body = b"ok"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self._cors()
                self.end_headers()
                self.wfile.write(body)
            elif path == "/snapshot":
                jpeg = buffer.latest()
                if jpeg is None:
                    self.send_error(503, "No frame yet")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpeg)))
                self.send_header("Cache-Control", "no-store")
                self._cors()
                self.end_headers()
                self.wfile.write(jpeg)
            elif path in ("/stream", "/"):
                self._serve_stream()
            else:
                self.send_error(404, "Not found")

        def _serve_stream(self):
            self.send_response(200)
            self.send_header(
                "Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}"
            )
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self._cors()
            self.end_headers()
            sequence = -1
            try:
                while True:
                    jpeg, sequence = buffer.wait_for_next(sequence)
                    if jpeg is None:
                        return
                    self.wfile.write(f"--{BOUNDARY}\r\n".encode())
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(
                        f"Content-Length: {len(jpeg)}\r\n\r\n".encode()
                    )
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return  # viewer closed the tab; entirely normal

    return Handler


class StreamServer:
    def __init__(self, host="0.0.0.0", port=8090):
        self.buffer = FrameBuffer()
        self._server = ThreadingHTTPServer((host, port), build_handler(self.buffer))
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self.port = port

    def start(self):
        self._thread.start()
        return self

    def publish(self, frame):
        self.buffer.publish(frame)

    def close(self):
        self.buffer.close()
        self._server.shutdown()
        self._server.server_close()
