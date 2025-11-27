# mjpeg_streamer.py
import cv2
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn


class MJPEGStreamer:
    """
    MJPEG streamer that pulls frames directly from a camera object.

    Usage:
        streamer = MJPEGStreamer(camera, port=8080)
        streamer.start()
        ...
        streamer.stop()
    """

    def __init__(self, camera, host="0.0.0.0", port=8080, path="/video", jpeg_quality=80):
        print("mjpeg init")
        self.camera = camera
        self.host = host
        self.port = port
        self.path = path
        self.jpeg_quality = int(jpeg_quality)
        self.camera_lock = threading.Lock()

        self._server = None
        self._thread = None
        self._stop_flag = threading.Event()

    def start(self):
        print("mjpeg start")
        """Start the MJPEG server in a background thread."""
        if self._thread is not None:
            return  # Already running

        # Define inner classes inside start() so they capture self
        parent = self

        class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        class StreamingHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != parent.path:
                    self.send_error(404)
                    return

                self.send_response(200)
                self.send_header("Age", "0")
                self.send_header("Cache-Control", "no-cache, private")
                self.send_header("Pragma", "no-cache")
                self.send_header(
                    "Content-Type",
                    "multipart/x-mixed-replace; boundary=FRAME"
                )
                self.end_headers()

                encode_params = [
                    int(cv2.IMWRITE_JPEG_QUALITY), parent.jpeg_quality
                ]

                while not parent._stop_flag.is_set():
                    with parent.camera_lock:
                        ret, frame = parent.camera.read()

                    if not ret or frame is None:
                        time.sleep(0.05)
                        continue

                    ok, jpg = cv2.imencode(".jpg", frame, encode_params)
                    if not ok:
                        continue

                    data = jpg.tobytes()

                    try:
                        self.wfile.write(b"--FRAME\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(
                            f"Content-Length: {len(data)}\r\n\r\n".encode()
                        )
                        self.wfile.write(data)
                        self.wfile.write(b"\r\n")
                        time.sleep(0.01)

                    except (BrokenPipeError, ConnectionResetError):
                        return  # Client disconnected

            def log_message(self, *args):
                return  # Silence logging

        # Create and launch server
        self._server = ThreadedHTTPServer((self.host, self.port), StreamingHandler)

        def run_server():
            try:
                self._server.serve_forever()
            except Exception as e:
                print("MJPEG server stop:", e)

        self._thread = threading.Thread(target=run_server, daemon=True)
        self._thread.start()

        print(f"[MJPEG] Streaming on http://{self.host}:{self.port}{self.path}")

    def stop(self):
        """Stop the MJPEG server."""
        if self._server:
            self._stop_flag.set()
            self._server.shutdown()
            self._server.server_close()

        if self._thread:
            self._thread.join(timeout=1)

        self._server = None
        self._thread = None
        self._stop_flag.clear()

        print("[MJPEG] Stream stopped.")
