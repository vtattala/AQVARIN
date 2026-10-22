# Third-party components

| Component | Source | License | Use |
| --- | --- | --- | --- |
| Autonomous-Drone-MSAR | https://github.com/InvictusRex/Autonomous-Drone-MSAR | No license file found in source checkout; rights need confirmation before redistribution | Maritime weights, sample videos, and original reference code |
| Ultralytics | https://github.com/ultralytics/ultralytics | AGPL-3.0 or commercial license | YOLO inference and BoT-SORT / ByteTrack |
| OpenCV | https://github.com/opencv/opencv | Apache-2.0 | Video input/output and drawing |
| FastAPI | https://github.com/fastapi/fastapi | MIT | Mobile-facing API |
| PyTorch | https://github.com/pytorch/pytorch | BSD-style | Model runtime, device selection |
| SAHI | https://github.com/obss/sahi | MIT | Optional sliced inference and duplicate merging |
| drowning-detection-system | https://github.com/yashpotdar-py/drowning-detection-system | MIT code; supplied AI Drone Lifeguard dataset CC BY 4.0 | Trained three-class best.pt and reference evaluation data |
| AI Drone Lifeguard | https://universe.roboflow.com/ai-drone-lifeguard/ai-drone-lifeguard/dataset/6 | CC BY 4.0 | Training data provenance for the supplied drowning checkpoint |
| drowning-detection (Z5cc) | https://github.com/Z5cc/drowning-detection | No top-level license file supplied | Optional temporal architecture and training workflow; no supplied trained checkpoint |
| Montserrat | https://github.com/googlefonts/Montserrat | SIL Open Font License 1.1; copy in mobile/assets/fonts/OFL.txt | Bundled Semibold and Bold UI fonts |
| Poppins | https://github.com/google/fonts/tree/main/ofl/poppins | SIL Open Font License 1.1; copy in mobile/assets/fonts/Poppins-OFL.txt | Bundled Regular, Medium, and Semibold labels, controls, and body text |

| RipScout | https://github.com/fahimhkhan/ripscout | UC Santa Cruz Noncommercial License; commercial use requires separate permission | Trained sediment_rip MobileNet SSD TFLite model; license and pinned hashes in assets/models/ripscout |
| LiteRT | https://github.com/google-ai-edge/LiteRT | Apache-2.0 | Independent TFLite inference runtime |

Companion model hashes and pinned revisions are in `assets/models/provenance.json`.
The original maritime checkpoint is not replaced. The additional generic person
checkpoint is Ultralytics YOLOv8n, under the same Ultralytics license above.

Review the licenses and weight provenance before public distribution of this project.

## Nationwide beach catalogue

`mobile/src/discover/data/us-beaches.json` combines active beach locations from
EPA's public BEACON `WQP_Beaches` service and nonhistorical Beach-class locations
from USGS GNIS Domestic Names, with nearby matching names deduplicated. These
U.S. government geographic records are attributed to EPA / USGS in the app.
The original 14 curated San Diego entries remain, with their existing IDs.
`data/provenance.json` records retrieval time, source URLs and input SHA-256s.
No third-party photographs, live water-quality status, or operating-hours data
are copied into the catalogue. Geographic names do not establish public access.

City/ZIP lookup uses Open-Meteo geocoding, based on GeoNames; attribution appears
in the place picker. API terms and availability still apply.
