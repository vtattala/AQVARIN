"""Camera protocol tests; no physical camera or ML dependencies required."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location('pi_camera', Path(__file__).resolve().parents[1]/'scripts/pi_camera.py')
pi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pi)
JPEG = b'\xff\xd8test-camera-frame\xff\xd9'
TOKEN = 'test-only-camera-token-123456789'


class FrameTests(unittest.TestCase):
    def test_latest_only_and_stale_rejection(self):
        now = [10.0]
        feed = pi.LatestFrame(clock=lambda: now[0])
        feed.write(JPEG);feed.write(JPEG+b'bad')
        self.assertEqual(feed.latest(timeout=0)[1], 0)
        feed.write(b'\xff\xd8new\xff\xd9')
        self.assertEqual(feed.latest(after=0, timeout=0)[1], 1)
        with self.assertRaises(TimeoutError):feed.latest(after=1, timeout=0)
        now[0] += 3
        with self.assertRaises(TimeoutError):feed.latest(timeout=0)

    def test_blocked_reader_gets_new_frame_and_stop_unblocks(self):
        feed = pi.LatestFrame();result = []
        thread = threading.Thread(target=lambda: result.append(feed.latest(timeout=1)))
        thread.start();feed.write(JPEG);thread.join(2)
        self.assertEqual(result[0][0], JPEG)
        feed.stop()
        with self.assertRaises(TimeoutError):feed.latest(timeout=0)

    def test_token_is_stable_and_not_world_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'token'
            first = pi.camera_token(path)
            self.assertEqual(first, pi.camera_token(path))
            self.assertGreaterEqual(len(first), 24)
            self.assertEqual(path.stat().st_mode & 0o077, 0)
            path.write_text('short')
            with self.assertRaises(ValueError):pi.camera_token(path)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.feed = pi.LatestFrame();self.feed.write(JPEG)
        self.server = pi.CameraServer(('127.0.0.1', 0), pi.make_handler(self.feed, TOKEN, {'width':1280,'height':720,'capture_fps':10}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True);self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.feed.stop();self.server.shutdown();self.server.server_close();self.thread.join(2)

    def request(self, path, auth=True, origin=None, method='GET'):
        headers = {'Authorization':'Bearer '+TOKEN} if auth else {}
        if origin:headers['Origin']=origin
        return urlopen(Request(self.base+path, headers=headers, method=method), timeout=4)

    def test_health_and_frame_require_token(self):
        for path in ['/api/camera/health','/api/camera/frame']:
            with self.assertRaises(HTTPError) as caught:self.request(path,auth=False)
            self.assertEqual(caught.exception.code,401)
        with self.request('/api/camera/health') as response:
            self.assertEqual(json.load(response)['status'],'ready')

    def test_valid_jpeg_has_freshness_headers_and_is_not_cached(self):
        with self.request('/api/camera/frame?after=-1',origin='http://localhost:8765') as response:
            self.assertEqual(response.read(),JPEG)
            self.assertEqual(response.headers['X-Camera-Sequence'],'0')
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertEqual(response.headers['Access-Control-Allow-Origin'],'http://localhost:8765')
            self.assertIn('X-Camera-Sequence',response.headers['Access-Control-Expose-Headers'])

    def test_browser_preflight_and_unapproved_origin(self):
        with self.request('/api/camera/frame',auth=False,origin='http://192.168.1.10:8081',method='OPTIONS') as response:
            self.assertEqual(response.status,204)
            self.assertIn('Authorization',response.headers['Access-Control-Allow-Headers'])
        with self.assertRaises(HTTPError) as caught:self.request('/api/camera/frame',origin='https://unapproved.example')
        self.assertEqual(caught.exception.code,403)

    def test_invalid_sequence_unknown_path_and_camera_failure(self):
        for path,code in [('/api/camera/frame?after=bad',400),('/no-such-path',404)]:
            with self.assertRaises(HTTPError) as caught:self.request(path)
            self.assertEqual(caught.exception.code,code)
        self.feed.stop()
        with self.assertRaises(HTTPError) as caught:self.request('/api/camera/health')
        self.assertEqual(caught.exception.code,503)


if __name__ == '__main__':unittest.main()
