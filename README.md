# AQVARIN — Water Intelligence

Mobile video and live-camera analysis for maritime object identification,
swimmer tracking, possible drowning review, and visible sediment-rip candidates.
This snapshot contains the latest upload and live pipelines tested on October 20, 2026.

## Included functionality

- Video upload, annotated playback, object counts and class observations.
- Swimmer, boat, buoy, jetski and life-saving-appliance identification.
- Swimmer identity continuity and explicit last-known markers during visual contact loss.
- Imported trained drowning classifier with temporal warning evidence and a review catalog.
- Independent RipScout analysis, bounded full-scene crop search and separate unconfirmed rip indicators.
- Continuous CameraX frames on Android; browser camera and iOS fallback implementations.
- AQVARIN branding, Poppins/Montserrat typography, Android permissions and Pixel build/install scripts.

**Current architecture:** the app sends video or camera frames to the Python
analysis process on a computer. The model files are included here, but inference
is not yet implemented on the phone. No cloud deployment or offline conversion
is included in this snapshot.

## Beach discovery

The **Discover** tab explores 22,228 beach records across 170 countries and
territories on a clustered world map. Search beach names and multilingual aliases,
filter by country or U.S. state, find a city worldwide, explore nearby beaches,
compare available swimming/surfing forecasts, and save favorites. Ocean forecasts
are shown where supported. Forecast alerts cover every saved beach worldwide,
with official warnings additionally available for U.S. beaches and territories. Water quality and local closures are not automatically monitored.
Discovery does not need the analysis computer.

Run `npm ci` inside `mobile`, then `npm run web`. Native apps must be rebuilt for
the added location/notification modules; the old Pixel APK is unchanged. Background
alert delivery is OS-scheduled and may be delayed. See
[discovery setup, data sources and limits](docs/beach-discovery.md).

## Quick start (Windows, Python 3.12, Node.js)

```powershell
gh repo clone vtattala/AQVARIN
cd AQVARIN
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe scripts/setup_action_models.py
.\.venv\Scripts\python.exe scripts/setup_ripscout.py
cd mobile
npm ci
cd ..
.\.venv\Scripts\python.exe scripts/start_pelagos.py
```

Open http://localhost:8081/ for the app and http://localhost:8000/docs for the API.
The historical `start_pelagos` script name remains for compatibility; the app is AQVARIN.
`requirements.txt` lists supported dependency ranges; `requirements-lock.txt`
pins the environment used for this snapshot. CPU inference works, but live
analysis can be much slower than the verified GPU configuration.

### Optional live GPU runtime

On a compatible NVIDIA Windows system, run:

```powershell
.\.venv\Scripts\python.exe scripts/setup_live_gpu.py
```

This installs a separate CUDA runtime and creates `config/live-runtime.local.json`.
Its machine-specific paths are not committed. Only live worker processes use it;
the original CPU upload environment and model weights stay intact.

## Pixel 6 APK

The private GitHub release **v0.1.0-pixel6-test** contains the tested standalone
APK, its SHA-256 build metadata and permission/signature verification report.
Download into the directory used by the installer:

```powershell
gh release download v0.1.0-pixel6-test --repo vtattala/AQVARIN --dir outputs/android -p AQVARIN-Pixel6-test.apk -p build-info.json -p verification.json
.\.venv\Scripts\python.exe scripts/install_pixel.py
```

Use an authorized USB or paired wireless ADB connection. The installer preserves
app data and forwards phone port 8000 to the computer's analysis service. Keep the
computer and debugging connection running. This is a private test build signed
with a local Android debug key, not a Play Store release. Signing keys are not
included. Rebuilding on another computer creates a different debug signature.

To build locally, install Android Studio with SDK/JDK and run
`python scripts/build_android.py` using the project virtual environment.
See [Pixel testing](docs/pixel-6-testing.md) and [mobile setup](mobile/README.md).

## Models and provenance

All four active checkpoints are included and recorded by SHA-256 in
`SOURCE_MANIFEST.json` and the companion model manifests:

| Model | Location | Source |
| --- | --- | --- |
| Maritime identification | `YOLOv8n Results & Metrics/weights/best.pt` | [Autonomous-Drone-MSAR](https://github.com/InvictusRex/Autonomous-Drone-MSAR), source commit `4dbb9d7` |
| Drowning actions | `assets/models/drowning_yolov8n.pt` | [drowning-detection-system](https://github.com/yashpotdar-py/drowning-detection-system), pinned manifest |
| Person corroboration | `assets/models/person_yolov8n.pt` | Upstream Ultralytics YOLOv8n, pinned manifest |
| Sediment-rip candidates | `assets/models/ripscout/detect1.tflite` | [RipScout](https://github.com/fahimhkhan/ripscout), pinned manifest |

Rejected training experiments and alternate checkpoints are not active or bundled.
Their evaluation outcomes are documented. Z5cc is an optional source integration;
its trained checkpoint was not supplied and is not the active drowning backend.
The original MSAR readme is preserved in [upstream documentation](docs/upstream-msar-readme.md).
See [third-party notices](THIRD_PARTY.md), including RipScout's noncommercial license.
No blanket license is asserted over third-party weights or upstream source.

## Verification

```powershell
$env:RUN_VIDEO_TEST='1'
.\.venv\Scripts\python.exe -m pytest -q
cd mobile
npm run typecheck
```

The opted-in suite exercises actual checkpoints, real upload processing and
sliced inference using the public upstream sample videos included here.
A few tests skip when optional external datasets or local historical audit
fixtures are absent; private test captures are not included in this repository.
The release verification document records exact clean-snapshot test results.

The user confirmed both live drowning catalog warnings and live rip warnings on
Pixel 6. The latest live rip scheduling applies globally: whole-frame inference
always runs, at most one crop follows an existing candidate, and at least two
crop slots keep rotating through the scene. No clip name/hash or hand-picked
video segment controls the live rip search. Multiple independent regions can warn.

## Practical limits

- Warnings are possible-distress/current review evidence, not calibrated safety probabilities.
- Fully invisible swimmers have last-known markers; these are not observed underwater detections.
- RipScout covers visible sediment-plume patterns, not every type of rip current.
- A small portrait-framed regression still misses the rip. Broad accuracy has not been established.
- Low sampling rates, camera movement, occlusion and scene changes can reduce recall.
- The API is currently for local testing, without production authentication/TLS.

Further details: [live camera](docs/live-camera.md), [drowning integration](docs/drowning-integration.md),
[rip-current integration](docs/rip-current-integration.md).
