# AQVARIN app

**Pixel 6 APK:** run `Build Android APK.cmd` in the project root to build a
standalone Android test APK, then `Install on Pixel 6.cmd` with USB debugging
authorized. `Connect Pixel USB.cmd` restores the API connection after reconnect.
See `docs/pixel-6-testing.md`. The phone still uses this computer for inference.

**Live camera:** choose the Live tab, then Start live camera. The camera preview
runs continuously while the server analyzes the newest captured frames. The
annotated frame and its latency appear separately. Stopping, leaving the page,
or backgrounding the app stops the camera. Monitor retains uploaded-video review.

For web camera access, use localhost on the computer or HTTPS for both app and
API; HTTP LAN URLs on phones cannot access the camera. Native Android/iOS builds
include Expo Camera and need rebuilding after this update. See
`docs/live-camera.md` in the project root for the transport contract and limits.

Double-click `Start AQVARIN.cmd` in the project root to start both local services.
The launcher supervises them and restarts exited processes. Uploaded queued jobs
save their processing settings and resume after an API restart. Browser uploads
use the browser host, retry transient failures without duplicating jobs, and
automatically reconnect while waiting for results. After a computer reboot, run
the launcher again; it does not change Windows login/startup settings.

Basic Expo / React Native app for Android, iOS and web. Opens directly to video
analysis. The model runs on the existing Python server on your computer.

From the project root, start the API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn vision.api:app --host 0.0.0.0 --port 8000
```

In a second terminal:

```powershell
cd mobile
npm install
npm start
```

Open with Expo Go compatible with SDK 57 on a phone on the same Wi-Fi, or press
`w` for the browser. Server URL is editable in the app; this computer currently
uses `http://10.0.0.2:8000`. Override the initial URL with `EXPO_PUBLIC_API_URL`.
The backend is local development software. No hosted backend or phone-local model
is configured. Windows cannot build native iOS binaries; that requires macOS/EAS.

Select a video, run analysis, then play or step through results. Tap an object for
its box, confidence, velocity, heading, history length and continuity details.
Filter by class. Recent job references are saved on-device; videos/data remain on
the server under `outputs/jobs`. Both analysis profiles use the existing checkpoint.
The recent-test profile uses confidence 0.10, tracker high/new thresholds 0.30 and
buffer 60, matching the previous CLI runs. Original API defaults remain available.
No camera-specific polygon is automatically applied to new videos.

Validation:

```powershell
npm run typecheck
npx expo install --check
npm run export
```

Android, iOS and web bundles were exported; the browser upload, real inference,
H.264 playback, frame stepping, class filtering and saved-result reopening were
tested. Native installation and playback on a physical phone have not been tested.

API encodes a separate H.264 playback copy after analysis. Original annotated
frames, tracking JSONL and model checkpoint are retained.
