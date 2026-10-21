# Live camera analysis

Open AQVARIN, select **Live** in the bottom navigation, choose a camera/scene,
and press **Start live camera**. Grant the browser/device camera permission.
The existing Monitor/upload workflow and saved job files are preserved.

## How frames flow

1. The camera preview runs continuously. On web, `getUserMedia` streams the
   selected camera to a video element. Android uses the local CameraX module
   in `mobile/modules/aqvarin-frame-camera`: preview + continuous image analysis,
   requesting the next frame only when transport is ready. It closes every
   `ImageProxy` and uses `KEEP_ONLY_LATEST`. iOS uses Expo Camera. Audio is disabled.
2. The client opens a live session, then repeatedly captures the current frame,
   resizes it to at most 1280 px on its longest edge, encodes JPEG, sends it,
   and waits for the result. No recorded video or file-upload job is involved.
3. Only one frame may be in flight. There is no queue of old camera frames.
   Each request carries a monotonic sequence and capture timestamp. Duplicate
   and out-of-order frames are rejected.
4. The server runs the original maritime checkpoint, the imported trained
   drowning model/person corroboration, and RipScout. It returns tracked
   objects/actions, last-known swimmer markers, model health, warnings,
   processing time, and an annotated JPEG of the exact analyzed frame.
5. The UI shows the smooth camera preview and the latest analyzed frame
   separately. Boxes therefore are never overlaid onto a newer camera image.
   Capture-to-result latency, analysis FPS, and result age are displayed.

## Preservation and live-specific policy

- ML workers run in separate spawned processes. Their CPU thread configuration,
  model instances and ID state do not change uploaded-video inference.
- `scripts/setup_live_gpu.py` installs verified CUDA PyTorch/torchvision in a
  separate runtime. `config/live-runtime.local.json` selects those packages only
  inside the camera worker, before importing torch. The original CPU `.venv`
  remains intact. Identification model status reports its actual device.
- Live association uses a class-aware Hungarian IoU matcher, then the existing
  swimmer appearance/camera-motion identity layer. It avoids Ultralytics'
  global tracker counter. IDs persist within a session; restarting a session
  starts a new namespace. Ambiguous/long disappearances can get new IDs.
- Like upload tracking, live detects at 0.1, starts tracks at 0.3, and uses
  weaker spatial matches only to continue an existing track. Generic person
  detections recover recent, unambiguously matched known swimmers; they do not
  establish water context in all-object mode. Confidence is never inflated.
- The shared drowning model's default video behavior is unchanged. Live caps
  extra small-swimmer crop passes to four per frame, rotating across swimmers
  and prioritizing recent lost positions. Full-frame model inference remains
  at the existing resolution. Small swimmers may be missed between crop turns.
- Live also checks the full camera image at the model's training resolution
  (640) and at 960, as well as the original 1280 pass. This addresses a measured
  portrait-frame failure at 1280 with a strong positive at 640. Results are
  deduplicated and share one timestamp, so three scales cannot supply three
  temporal votes. Independent image tiles periodically search for swimmers that
  never received a maritime box; tile-only warnings retain the stronger crop
  evidence policy. Search batches are bounded to six on CUDA or two on CPU.
- Standard live warnings retain the existing confidence/peak/count criteria. To support
  slower CPU sampling, distinct predictions may span a six-second window,
  with evidence reset after capture gaps over 2.5 seconds. Offline default
  windows remain two seconds. Live rip regions use the same six-second window.
- A second live-only review rule combines two distinct, full-frame active
  drowning predictions (both >=0.65, peak >=0.8, spanning >=0.2 seconds) with
  0.75–3 seconds of observed visual-contact loss. It excludes crop-only evidence,
  stale evidence, scene cuts, and capture gaps; scores average the actual two
  predictions. Missing visibility never becomes a third neural vote or a
  claimed underwater detection. A lone disappearance cannot generate a warning.
- Threatened swimmers get priority for search crops and an explicit last-known
  marker for up to eight seconds. Ordinary missing markers expire after three
  seconds. Search crops expire after three seconds. Strong swimming evidence
  still clears drowning votes; no new action score is assigned to hidden people.
- No camera calibration is inferred. Pixel motion is not offshore velocity.
  RipScout still detects sediment-plume candidates, not all rip types.
- The live rip branch also searches at most three overlapping context crops per
  camera frame, retaining the whole-frame pass. Coordinates map back to the
  camera image. Matching views are deduplicated and count as one temporal
  observation. Crop-only warnings need a peak >=0.75 in addition to three
  independent overlapping predictions spanning at least one second. Crops reset
  after cuts/dimension changes/gaps and do not affect swimmer/drowning inference.
  At most one crop follows a previous candidate; at least two discovery slots
  keep rotating through the entire set of context views. Existing positives
  cannot monopolize the search. Diagnostics report actual per-view coverage.
  No filename, source hash, clip section or manually selected target position
  controls this search. Separated model regions are all passed to evidence
  tracking; a warning for one region does not prevent warnings for other regions.
- Rip candidates that have not met the persistence/peak criteria are visible
  separately in **Rip indicators needing review**. Metadata diagnostics include
  rip model state, candidate boxes, evidence counts and the searched views.
- Confidence scores and persistence are review evidence, not validated drowning
  or current probabilities. Low sampling rates can miss short actions entirely.

## Resource management and errors

Stopping, switching pages, hiding the browser page, or backgrounding the app
aborts transport, releases the camera, and closes the live session. Native
temporary JPEGs are deleted after each capture. The server does not save live
images or reports. Only the latest 50 warnings per type are retained in memory.

The server accepts at most two live sessions, expires idle sessions after 120
seconds and sessions older than one hour, and runs cleanup every 30 seconds.
Requests are bounded to 2 MB JPEG, at most four megapixels and 2560 px per edge.
One busy session cannot queue another inference request. Sidecar failure is
reported while identification continues. Primary inference/transport failure
stops the stream and asks the user to restart. It does not keep showing a
stale image as an active feed.

`GET /api/live/sessions/{id}/diagnostics` returns up to 120 in-memory metadata
samples (swimmer positions, model actions/rejections, cuts, timing, warnings).
It retains no camera images and disappears when the session closes.

The local-only `diagnostic-frame` endpoint explicitly exports the single current
JPEG held in memory; LAN callers receive 403. `scripts/capture_live_sample.py`
can save a bounded, user-requested camera debugging sample. It ignores Python
file-replay sessions. This is an explicit developer export; normal live
processing writes no camera images to disk.

The review catalog separates persistent warnings from historical unconfirmed
drowning indicators, preserving their actual model scores and observation
counts. One weak proposal is not silently promoted to a confirmed warning.

`scripts/train_live_camera.py` trains a separate candidate from the upstream
labeled training split with perspective/blur/JPEG augmentation. Original valid
and test splits are unchanged. The candidate stays disabled until evaluated;
`config/live-model.local.json` can activate a SHA-verified candidate for live
only. The imported upload checkpoint and provenance manifest are unchanged.
The October 20 candidate was rejected: held-out test recall decreased from
0.519 to 0.403 and mAP50 from 0.449 to 0.417. It remains disabled. The active
fix uses the original checkpoint with multiscale inference.

Camera permission denial, missing/disconnected/busy cameras, insecure origins,
pending permission timeout, invalid server URL and unavailable models have
explicit messages. Browsers require localhost or HTTPS for camera access.
An HTTP LAN address on a phone is insufficient; use the native app or configure
HTTPS for both app and API. There is no built-in public hosting/tunnel.

Native camera permissions are configured with the SDK-compatible Expo Camera
plugin. Android must be rebuilt for changes to the local frame camera module.

## Verification and remaining acceptance check

Tests cover all model branches using controlled predictions, independent session
IDs, swimmer loss/reacquisition, warning evidence at slow wall-clock sampling,
frame validation, stale frames, concurrent requests, capacity and cleanup.
The real live HTTP API was exercised with all three trained models using a
saved clip as a camera substitute. Source and existing job outputs were hashed
before/after; they remained unchanged.

Before refinement, crowded pool analysis took 1.2–1.7 seconds per frame on CPU
and missed its initial warning. With the isolated RTX 4070 runtime, a real HTTP
wall-clock replay produced the warning at 0.71 seconds, median processing
213.5 ms. A second replay while compiling Android produced it at 1.11 seconds.
The sediment-rip sample produced a warning at 1.19 seconds, median processing
108.7 ms. The sampled normal aerial-swimming and yacht clips produced no
drowning/rip warnings. These are regression examples, not a held-out accuracy
evaluation and not proof that every visible swimmer is detected.

Pixel 6 installation and the continuous CameraX stream were observed: 29
frames arrived in 11.5 seconds, with typical gaps of 0.35–0.52 seconds. The user
confirmed that this run still missed the warning. Its metadata contained two
isolated candidates and no sustained target evidence. Afterward, full-frame
multiscale inference fixed a reproduced portrait scale failure: a real HTTP
portrait replay warned at 0.737 seconds, mean action score 0.907. The user subsequently confirmed on October 20 that the latest Pixel test
improved and warnings are now being cataloged. This is user-reported confirmation
of catalog behavior; the warning types were not independently audited and no
raw camera debugging sample was received. Wait until
“Live analysis” (model loading finished) before starting a short test clip.

### October 20 rip-current investigation

The supplied `Caught in a Rip Current ... 2026-10-12 23-38-09.mp4` reproduced a
model miss. The original checkpoint found two weak predictions at 2 Hz and no
warning; at 2.5 Hz with 1280 px frames it produced a late score-0.5 warning.
The stricter live crop search produced possible-rip review events on the wide
file replay, but **still produced no warning on the aspect-preserved portrait
fixture**. This limitation remains; file replay is not a physical Pixel test,
and the region locations have not been independently labeled for accuracy.

The alternate upstream `FPVDemo/Model/ripmodels/detect1.tflite` has the broader
`rip_current_T1` label. It was evaluated and **rejected**, because it produced
high-confidence false positives on the pool and yacht controls (including a
pool score of 0.996). It is saved as a disabled evaluation candidate under
`assets/models/ripscout/expanded/`; no app code loads it. The `detect3.tflite`
variant also failed to identify the supplied clip. Two external research/model
candidates were evaluated without activation; neither produced sustained
evidence on both the wide and portrait examples. Current results do not justify
calling broad rip-current detection solved. A broader detector needs validation
on labeled aerial footage and negative pool/boat/foam examples.

The final stricter crop rule produced no persistent rip warning on the sampled
wavepool, swimming and yacht controls. Confidence thresholds on the original
whole-frame checkpoint and all upload defaults are unchanged. Source and
checkpoint hashes plus regression outputs are in `outputs/live-rip-refinement`.

After installation, a camera-labelled portrait session produced five possible-rip
events in backend metadata (108 observed frames, first event at 15.25 seconds
into that session). This verifies that the camera-to-warning path is executing.
The user subsequently confirmed that the same rip-current clip now produces a
warning on the Pixel and described the result as "pretty solid." This is a
user-confirmed example, not validation of every rip type or every region.
Metadata was saved without exporting raw camera images. Subsequent search
fairness refinements apply when starting the next live session; the existing
camera session is left running so its current catalog is preserved.

Reproduce the real-model transport test with:

```
.venv\Scripts\python.exe scripts/check_live.py path\to\sample.mp4
```

This script samples the saved file using elapsed wall time and explicitly does
not claim to validate physical camera capture or permission prompts.
