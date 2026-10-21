# Source and Android release verification â€” October 20, 2026

- Clean exported source: `RUN_VIDEO_TEST=1`, **95 passed, 3 skipped**.
- Skips are optional external drowning-dataset images, historical yacht audit output,
  and a RipScout validation still; these are not deployment dependencies.
- Clean `npm ci` and TypeScript typecheck passed.
- Included all four active trained checkpoints and their hashes/provenance.
- Included the native continuous CameraX module, JS/TypeScript sources, fonts, branding,
  package lock, Python dependency pins and Android build/install scripts.
- Source manifest checked against every exported file; credential-pattern scan clean.
- Model weights and original identification/drowning code were preserved.
- Android signature, arm64 ABI, embedded JS, camera modules and permission list verified.
- Latest APK installed and launched on Pixel 6; user confirmed live drowning cataloging
  and possible-rip warnings. This does not establish all-rip/all-swimmer accuracy.
- Live API replay: supplied rip clip warned at 1.76 s; wavepool drowning warned at 1.09 s
  with no persistent rip alert. Global search refinement also passed separate-region
  and coverage-with-persistent-candidates checks plus swimming/yacht/pool controls.
- Global live rip search is independent of filenames and clip-specific coordinates.
  Two discovery slots continue rotating even when an existing candidate persists.
- Known limitation: a smaller synthetic portrait view still misses the rip. Broader
  candidate models were rejected for false positives or insufficient recall.
- Runtime remains computer/server-based; no cloud deployment or on-phone inference
  was added for this release. Local CUDA paths are recreated with setup_live_gpu.py.

This is a private testing snapshot, not a store-ready or safety-certified product.
