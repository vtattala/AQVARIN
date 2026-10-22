"""Camera Module 3 -> AQVARIN Live, for Raspberry Pi OS / Pi 4.

Only Picamera2's OS packages are needed on the Pi; analysis stays on the server
selected in AQVARIN. No audio, recording, model imports, or frame queues.
"""
import argparse
import hmac
import io
import json
import os
from pathlib import Path
import re
import secrets
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

MAX_BYTES = 2_000_000
MAX_AGE = 2.0
ROOT = Path(__file__).resolve().parent.parent
LOCAL_ORIGIN = re.compile(r'https?://(?:localhost|127\.0\.0\.1|10\.(?:\d+\.){2}\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|[a-zA-Z0-9-]+\.local)(?::\d+)?\Z')


class LatestFrame(io.BufferedIOBase):
    """The encoder replaces one frame. Slow readers cannot build a backlog."""
    def __init__(self, clock=time.monotonic):
        self.condition = threading.Condition()
        self.clock = clock
        self.sequence = -1
        self.frame = None
        self.created = 0.0
        self.closed_feed = False

    def write(self, data):
        if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9') or len(data) > MAX_BYTES:
            return len(data)
        with self.condition:
            self.frame = bytes(data)
            self.created = self.clock()
            self.sequence += 1
            self.condition.notify_all()
        return len(data)

    def latest(self, after=-1, timeout=2.0):
        with self.condition:
            self.condition.wait_for(lambda: self.closed_feed or self.sequence > after, timeout)
            age = self.clock() - self.created
            if self.closed_feed or self.frame is None or self.sequence <= after or age > MAX_AGE:
                raise TimeoutError('Camera is not delivering fresh frames. Check the cable and restart the Pi camera service.')
            return self.frame, self.sequence, age

    def stop(self):
        with self.condition:
            self.closed_feed = True
            self.condition.notify_all()


def camera_token(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        token = path.read_text().strip()
    else:
        token = secrets.token_urlsafe(32)
        with os.fdopen(fd, 'w') as stream:
            stream.write(token + '\n')
    if len(token) < 24 or not re.fullmatch(r'[A-Za-z0-9_-]+', token):
        raise ValueError('Camera token must contain at least 24 letters, digits, underscores or hyphens.')
    return token


def make_handler(output, token, metadata, allowed_origins=()):
    class CameraHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Never log credentials or one line per camera frame.

        def origin_allowed(self):
            origin = self.headers.get('Origin')
            return not origin or bool(LOCAL_ORIGIN.fullmatch(origin)) or origin in allowed_origins

        def send_payload(self, status, body=b'', content_type='application/json', extra=None):
            self.send_response(status)
            origin = self.headers.get('Origin')
            if origin and self.origin_allowed():
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Vary', 'Origin')
                self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
                self.send_header('Access-Control-Allow-Private-Network', 'true')
                self.send_header('Access-Control-Allow-Headers', 'Authorization')
                self.send_header('Access-Control-Expose-Headers', 'X-Camera-Sequence, X-Frame-Age-Ms')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if body:
                self.wfile.write(body)

        def error(self, status, message):
            self.send_payload(status, json.dumps({'detail': message}).encode())

        def do_OPTIONS(self):
            if not self.origin_allowed():
                self.error(403, 'This app origin is not allowed.')
            else:
                self.send_payload(204)

        def do_GET(self):
            if not self.origin_allowed():
                self.error(403, 'This app origin is not allowed.'); return
            if not hmac.compare_digest(self.headers.get('Authorization', '').encode('utf-8'), ('Bearer ' + token).encode('utf-8')):
                self.error(401, 'Enter the camera token printed by the Pi camera service.'); return
            parsed = urlsplit(self.path)
            if parsed.path == '/api/camera/health':
                try:
                    _frame, sequence, age = output.latest(timeout=0)
                    self.send_payload(200, json.dumps({**metadata, 'status': 'ready', 'sequence': sequence, 'frame_age_ms': round(age*1000)}).encode())
                except TimeoutError as exc:
                    self.error(503, str(exc))
            elif parsed.path == '/api/camera/frame':
                try:
                    after = int(parse_qs(parsed.query).get('after', ['-1'])[0])
                    if not -1 <= after <= 2**53-1:
                        raise ValueError()
                except ValueError:
                    self.error(400, 'Invalid camera frame sequence.'); return
                try:
                    frame, sequence, age = output.latest(after=after)
                    self.send_payload(200, frame, 'image/jpeg', {'X-Camera-Sequence': str(sequence), 'X-Frame-Age-Ms': str(round(age*1000))})
                except TimeoutError as exc:
                    self.error(503, str(exc))
            else:
                self.error(404, 'Use /api/camera/health or /api/camera/frame.')
    return CameraHandler


class CameraServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, *args, **kwargs):
        self.clients = threading.BoundedSemaphore(8)
        super().__init__(*args, **kwargs)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(8)
        return connection, address

    def process_request(self, request, address):
        if not self.clients.acquire(blocking=False):
            try:
                request.sendall(b'HTTP/1.0 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.clients.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.clients.release()


def open_camera(args, output):
    # Lazy imports keep the HTTP protocol testable without Pi hardware or model packages.
    try:
        from picamera2 import Picamera2
        from picamera2.encoders import MJPEGEncoder
        from picamera2.outputs import FileOutput
        from libcamera import Transform, controls
    except ImportError as exc:
        raise RuntimeError('Run with Raspberry Pi OS system Python after installing python3-picamera2. See docs/raspberry-pi-camera.md.') from exc
    camera = Picamera2(args.camera)
    try:
        config = camera.create_video_configuration(main={'size': (args.width, args.height), 'format': 'YUV420'},
                    controls={'FrameRate': args.fps}, buffer_count=4,
                    transform=Transform(hflip=args.rotation == 180, vflip=args.rotation == 180))
        camera.configure(config)
        if 'AfMode' in camera.camera_controls:
            camera.set_controls({'AfMode': controls.AfModeEnum.Continuous} if args.focus == 'auto' else {'AfMode': controls.AfModeEnum.Manual, 'LensPosition': 0.0})
        camera.start_recording(MJPEGEncoder(), FileOutput(output))
        output.latest(timeout=10)
        return camera
    except BaseException:
        camera.close()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--token-file', type=Path, default=ROOT/'config/pi-camera-token.local')
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    parser.add_argument('--fps', type=int, default=10)
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--rotation', type=int, choices=(0, 180), default=0)
    parser.add_argument('--focus', choices=('auto', 'infinity'), default='auto')
    parser.add_argument('--allow-origin', action='append', default=[])
    args = parser.parse_args()
    if not (320 <= args.width <= 1280 and 240 <= args.height <= 960 and args.width % 2 == 0 and args.height % 2 == 0 and 1 <= args.fps <= 15 and 1 <= args.port <= 65535 and args.camera >= 0):
        parser.error('Use even dimensions 320–1280 × 240–960, 1–15 FPS, and a valid camera/port.')
    token = camera_token(args.token_file)
    output = LatestFrame()
    camera = None
    try:
        camera = open_camera(args, output)
        metadata = {'source': 'AQVARIN Pi camera', 'width': args.width, 'height': args.height, 'capture_fps': args.fps, 'focus': args.focus}
        def terminate(*_args):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, terminate)
        with CameraServer((args.host, args.port), make_handler(output, token, metadata, args.allow_origin)) as server:
            print(f'AQVARIN Pi camera is ready on port {args.port}.\nIn Live, choose Raspberry Pi camera and enter this Pi’s LAN address.\nCamera token: {token}', flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        raise SystemExit(f'Pi camera could not start: {exc}') from exc
    finally:
        output.stop()
        if camera is not None:
            try:
                camera.stop_recording()
            finally:
                camera.close()


if __name__ == '__main__':
    main()
