# Drowning action integration

The identification model, tracker, thresholds and output JSONL are unchanged.
`vision.distress` reads that output after identification. Its failures are isolated
from the API job. The app exposes a separate distress report and review timestamps.

## Source and checkpoint

### Active default: trained YOLOv8n

The default backend is now `yolo`, using the actual trained `best.pt` from
https://github.com/yashpotdar-py/drowning-detection-system, pinned at
`21174a740fe9461af87183e8f96f34ca78f3fcdc`. This model has three labels:
Active drowning, Possible Passive Drowner, Swimming. Assets are installed in
`assets/models`, with class mapping and SHA-256 checked at load time. Reproduce
them with `.venv\Scripts\python.exe scripts/setup_action_models.py`.

The API preserves `tracks.jsonl` / `tracked.mp4` as the original identification
outputs. It serves `analysis.jsonl` / `analysis.mp4` after companion inference,
adds per-object action scores, and generates a separate persisted warning report.
`identification_summary` retains the original totals. Companion failures leave
the original results available. Existing saved jobs can be updated using
`scripts/refresh_analysis.py <job-id>` without rerunning or changing primary tracks.

Inference samples full frames at up to 10 Hz and separately examines small
tracked swimmer crops, including recent last-seen regions. Repeated cached frames
are not independent evidence. Full-frame alerts require three active or four
passive predictions in two seconds, with minimum scores 0.55 and peaks 0.8/0.9.
Crop-only alerts require five predictions spanning 0.6 seconds and peaks 0.9/0.95.
These thresholds are provisional, not calibrated probabilities. Scene cuts reset
evidence; brief gaps are tolerated. Separate dashed last-known markers expire
after 1.5 seconds and never provide a fabricated current detection or score.
An independent swimmer identity layer links compatible detections across gaps up
to eight seconds using position, motion, camera compensation and visible color
features. It preserves source tracker IDs in `source_track_id`, recomputes history
under the stable swimmer ID, and leaves detector boxes, confidences and action
scores unchanged. Ambiguous matches and scene cuts do not force identity merges.
This does not guarantee identity recovery through every occlusion in a crowd.
There is no temporal neural network in this checkpoint. The existing eight
indicator capability descriptions remain accurate; three action classes do not
establish individual arm, head, pose or submersion measurements.

The generic person/boat model corroborates conflicting labels. Independently
detected boat hulls veto action labels inside them, and oversized action boxes
need independent person support. Per-video no-boat annotations and the previously
reviewed beach tree region are in `config/reference_clips.json`, keyed by exact
source SHA-256. Those constraints are user/reference annotations, not newly
learned model capabilities, and do not apply to unknown clips. Original swimmer
fields are retained; optional `distress_action` metadata is added separately.

### Optional temporal backend: Z5cc

Upstream: https://github.com/Z5cc/drowning-detection

Pinned revision: `b75850a26cc8e6b255bd09ffb26c333adce4fa2a`.
Run `scripts/setup_drowning.ps1` to reproduce the ignored upstream checkout.
The upstream source is preserved, including its credits and dataset annotations.
It does not supply a trained checkpoint or a top-level license file. Review the
upstream authors' terms before redistribution. Do not package that checkout into
the mobile application.

For this optional backend, copy `config/drowning.example.json` to `config/drowning.local.json`, set `backend` to `z5cc`, set checkpoint
to a trained two-class swim/drown `.pth`, and set the architecture to the matching
upstream `2Dseq_tiny`, `2Dseq_medium`, `YOWOv2_tiny` or `YOWOv2_medium` configuration.
An alternate config path can be supplied with `AEGIS_DROWNING_CONFIG`.
Loading is strict and uses PyTorch's weights-only loader. Incompatible or missing
weights generate an unavailable status, never predictions from random weights.

The worker executes the upstream architecture in a separate Python process. It
uses upstream RGB 0–255 PIL resizing, normalized box output rescaling, 30 Hz
temporal sampling, recurrent state and scene-cut reset. Reference YOWOv2 waits
for its temporal window; recurrent output requires at least four seconds of
context before it can generate a warning. Scores are model action scores, not
calibrated drowning probabilities. The app shows only track-associated review
events; unmatched/ambiguous proposals remain in the actions JSONL for diagnosis.

## Movement and eight requested indicators

Low movement, speed reduction and swimmer separation are temporal image-space
proxies. Offshore drift additionally requires a direction pointing offshore in
image coordinates. For movement alerts, explicitly verify `water_confirmed`
and `motion_reference: stationary` or `stabilized` for the footage. This version
does not automatically stabilize drone footage or infer shoreline calibration.
The global config applies to all new jobs: leave it uncalibrated when uploading
mixed moving-camera videos. Existing water ROI settings do not independently
establish a valid camera reference.

Two persisted movement proxies, or a persisted matched upstream `drown` action,
produce a `possible_distress` review event. A resting swimmer alone does not.
The legacy temporal/movement rules reset on gaps; YOLO votes tolerate brief gaps.
Visual contact loss is reported separately and is not confirmed submersion.
Head/waterline position, frantic arm motion, body orientation and repeated
submersion remain explicitly unavailable pending a suitable estimator and labels.
The upstream swim/drown model does not explain those individual indicators.

## Training and acceptance gate

The upstream README describes reconstruction of its lifeguard YouTube dataset
using `dataset_utils/LifeguardUtils.py`, then `train.py --config 2Dseq_tiny`,
`eval.py --config 2Dseq_tiny --weight <checkpoint-name>` and the supplied fold
configs. Use a separate training environment following its requirements; do not
downgrade the working detector's environment. Dataset availability and usage
rights must be established before reconstruction.

Before using alerts operationally, evaluate held-out
drone clips containing confirmed distress, ordinary swimming, floating, waves,
camera motion and occlusion. Split by source video/location, measure false alerts
per minute and recall/time-to-warning at the event level, and calibrate thresholds.
Unit tests and normal beach footage do not establish drowning accuracy.

Standalone read-only run:

```powershell
.venv\Scripts\python.exe -m vision.distress <source.mp4> <tracks.jsonl> <distress.json>
```

Warnings require human review. No warnings does not establish swimmer safety.
