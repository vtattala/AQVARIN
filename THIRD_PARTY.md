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

## Worldwide geographic catalogue

GeoNames (https://www.geonames.org/), licensed under Creative Commons Attribution
4.0 (https://creativecommons.org/licenses/by/4.0/), supplies the worldwide beach
names, alternate names, coordinates, countries and regions in
`mobile/src/discover/data/world-beaches.json` and `countries.json`.
AQVARIN selects Beach / Beaches feature codes, rounds coordinates, limits aliases,
deduplicates nearby matching names and combines the results with U.S. records.
Attribution appears in the app and each record links to its GeoNames source.
`world-provenance.json` identifies the snapshot and input hashes. These records
are geographic features, not verified public recreational access points.

Leaflet 1.9.4 (https://leafletjs.com/) is BSD-2-Clause. The map uses OpenStreetMap
tiles with visible contributor attribution; https://www.openstreetmap.org/copyright.
OpenStreetMap beach records are not included in this catalogue snapshot.

## Beach photography and traveler information

Selected-beach article excerpts are from Wikipedia contributors; nearby travel
listing excerpts are from Wikivoyage contributors. Text is attributed, linked
and presented as excerpts under CC BY-SA 4.0:
https://creativecommons.org/licenses/by-sa/4.0/ . Source pages provide revision
histories and contributor credits. The copied text excerpts retain this license;
this does not relicense the app code.

Beach photographs are remotely displayed from Wikimedia Commons. Each image
retains its individual source license and author attribution, fetched via
imageinfo metadata and shown below the photo, with source and license links.
CC BY / CC BY-SA, CC0 and public-domain images are supported; unknown or
unsupported license metadata is not displayed. Cropping for the UI is indicated.
No third-party image files are bundled in this change. Information may be
incomplete or outdated; restaurant entries are not endorsements or live listings.
