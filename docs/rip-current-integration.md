# Rip-current analysis

October 20 live refinement: see `docs/live-camera.md` for bounded live context
search, separate unconfirmed candidates, and the unresolved portrait/non-sediment
miss. The alternate two-class RipScout checkpoint was tested and rejected for
false positives on pool/yacht controls; it is not active. This page's upload
contract and original model remain unchanged.

AQVARIN loads the supplied RipScout **MobileNetSSDRip** checkpoint from
`FPVDemo/Model/detect1.tflite`, pinned at commit
`9c42c5db12ae914137a022242a19612710a85b11`. This is a trained sediment-rip
detector, not a newly trained model or an optical-flow approximation.

## Contract

`vision/rip_current.py` runs independently after swimmer/drowning analysis.
It reads the original upload and writes only `rip_current.json`. It does not
change detector weights, tracking IDs, drowning scores, existing JSONL files,
or annotated videos. A runtime failure produces an unavailable rip report,
while identification remains successful. New uploads include this phase.
Previously saved jobs without the report explicitly ask for reanalysis.

The API adds `rip_current_url` and `/api/jobs/{id}/rip-current`. The report
contains original-frame pixel boxes, timestamps, independent sampled-frame
predictions, model scores, region IDs, and possible-rip review events.
The app draws candidate boxes on embedded playback and supports seeking to
warning timestamps. Native fullscreen playback shows the original annotated
video; the additional rip overlay is in the embedded player only.

## Inference and warnings

- Full-frame BGR to RGB conversion and 300x300 resize, uint8 input, matching
  the upstream executed Swift implementation (the crop comment is inaccurate).
- SSD postprocessed outputs: normalized yxyx boxes, zero-based classes, scores,
  count. Class 0 maps to labelmap line 1, `sediment_rip`; `???` is background.
- Upstream confidence threshold 0.5; sample at roughly 2 Hz.
- Review warning: three spatially overlapping independent predictions spanning
  at least one second within two seconds. Votes expire, scene cuts reset
  continuity, and cached frames cannot count multiple times.
- Region tracking is image-space continuity, not physical current tracking.
  No GPS, shoreline geometry, offshore speed, or swimmer exposure is inferred.
- Scores and persistence do not confirm hydrodynamic flow or swimmer safety.

## Verification

64 automated tests passed including real-checkpoint smoke inference, coordinate
mapping, temporal evidence, API compatibility, source preservation, and existing
identification/drowning regressions. Android/iOS/web export and TypeScript checks
were run. Native playback overlay still needs device verification.

Four annotated stills were extracted with HTTP range requests from the dataset
linked by the current RipScout README (the old dataset.md folder links returned
404). No full 737 MB dataset download was needed. The bundled checkpoint found
both examples labeled `sediment_rip`: scores 0.883 and 0.691, bounding-box IoUs
0.814 and 0.804. It missed both examples labeled `rip_current`. These are small
repository-associated sanity checks with unknown training overlap, **not** a
held-out accuracy measurement. Results are saved in
`outputs/ripscout-validation/results.json`.

Three saved user clips were analyzed without rerunning any other model; hashes
of tracking/action/distress outputs stayed identical. The wavepool clip produced
zero candidates and zero rip warnings. One other saved clip produced one
transient candidate and no warning. Details: `outputs/ripscout-regression.json`.

For broader detection, evaluate labeled drone footage with both sediment and
non-sediment rips, wave breaks, shadows, foam, boats, and moving cameras; train
or fine-tune a broader detector if this checkpoint fails that evaluation. Do not
lower thresholds to imply accuracy the checkpoint does not have.

## Installation and provenance

Install `requirements.txt`; run `scripts/setup_ripscout.py` to restore verified
assets. SHA-256 hashes, upstream revision, citation, and the upstream UC Santa
Cruz Noncommercial License are bundled in `assets/models/ripscout`. Commercial
use requires permission under that license. No DJI flight-control code is run.
