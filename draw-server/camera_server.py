"""Shared, cropped drawing-bed camera frames for the public drawing page."""
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import signal
import subprocess
import threading
import time
from urllib.parse import urlsplit


HOST = "127.0.0.1"
PORT = 8766
UPSTREAM = os.getenv("DRAW_CAMERA_UPSTREAM", "http://100.107.130.73:8080/stream")
FILTER = "fps=10,crop=760:650:610:190,hflip,vflip"
ALLOWED_HOSTS = {
    "127.0.0.1:8766",
    "localhost:8766",
    "gabepi.tail0cb95e.ts.net:8443",
}
ALLOWED_REFERER_HOSTS = {"gabrielkahen.com", "www.gabrielkahen.com"}
latest = (b"", 0.0)
frame_lock = threading.Lock()
rate_lock = threading.Lock()
requests = defaultdict(deque)
stopping = False


def capture(pipe):
    global latest
    buffer = bytearray()
    while chunk := pipe.read(65536):
        buffer.extend(chunk)
        while True:
            start = buffer.find(b"\xff\xd8")
            if start < 0:
                buffer[:] = buffer[-1:]
                break
            if start:
                del buffer[:start]
            end = buffer.find(b"\xff\xd9", 2)
            if end < 0:
                break
            frame = bytes(buffer[: end + 2])
            del buffer[: end + 2]
            with frame_lock:
                latest = (frame, time.monotonic())
        if len(buffer) > 4 * 1024 * 1024:
            buffer.clear()


def allowed_request(handler):
    if handler.headers.get("Host") not in ALLOWED_HOSTS:
        return False
    if handler.headers.get("Sec-Fetch-Site") == "cross-site":
        referer = urlsplit(handler.headers.get("Referer", ""))
        if (
            handler.headers.get("Sec-Fetch-Dest") != "image"
            or referer.scheme != "https"
            or referer.hostname not in ALLOWED_REFERER_HOSTS
        ):
            return False
    return True


def rate_limited(handler):
    forwarded = handler.headers.get("X-Forwarded-For", "")
    client = forwarded.split(",", 1)[0].strip() or handler.client_address[0]
    now = time.monotonic()
    with rate_lock:
        history = requests[client]
        while history and history[0] < now - 2:
            history.popleft()
        if len(history) >= 16:
            return True
        history.append(now)
        if len(requests) > 1024:
            for key in [key for key, value in requests.items() if not value or value[-1] < now - 30]:
                requests.pop(key, None)
    return False


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("/health", "/draw-camera/health"):
            with frame_lock:
                _, stamp = latest
            body = json.dumps({"status": "ok" if time.monotonic() - stamp < 2 else "waiting"}).encode()
            self.respond(200, body, "application/json")
            return
        if path not in ("/frame.jpg", "/draw-camera/frame.jpg"):
            self.send_error(404)
            return
        if not allowed_request(self):
            self.send_error(403)
            return
        if rate_limited(self):
            self.send_response(429)
            self.send_header("Retry-After", "1")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        with frame_lock:
            body, stamp = latest
        if not body or time.monotonic() - stamp > 2:
            self.send_error(503, "Camera frame unavailable")
            return
        self.respond(200, body, "image/jpeg")

    def respond(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *_):
        pass


def main():
    global stopping

    def stop(*_):
        global stopping
        stopping = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    process = subprocess.Popen(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-i", UPSTREAM, "-an", "-vf", FILTER,
            "-c:v", "mjpeg", "-q:v", "5", "-f", "image2pipe", "pipe:1",
        ],
        stdout=subprocess.PIPE,
    )
    reader = threading.Thread(target=capture, args=(process.stdout,), daemon=True)
    reader.start()
    with Server((HOST, PORT), Handler) as server:
        server.timeout = 0.5
        print(f"Drawing camera: http://{HOST}:{PORT}", flush=True)
        try:
            while not stopping and process.poll() is None:
                server.handle_request()
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            reader.join(timeout=1)
            process.stdout.close()
    if not stopping and process.returncode:
        raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
