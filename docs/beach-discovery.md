# Worldwide beach discovery

Discover includes **22,228 records across 170 countries and territories**, plus
three records without a country assignment. GeoNames worldwide records supplement
the existing EPA / USGS U.S. catalogue. Country and U.S. state filters, Unicode and
alternate-name search, worldwide city lookup, distance search, clustered mapping,
12-result pages, favorites and supported forecasts work across the catalogue.
Coverage varies substantially: this is not every beach. Existing upload/live
analysis is unchanged, and discovery does not need the analysis computer.

## Run and verify

From `mobile`:

```sh
npm ci
npm run typecheck
npm run test:discover
npm run web
```

Native apps need a rebuild (`npm run android` / `npm run ios`) for the location,
notification and background modules added with Discover. The original Pixel APK
is unchanged. A JavaScript export does not establish physical-device notification
permission or background scheduling behavior.

## Catalogue and coverage

`world-beaches.json` contains 16,203 GeoNames Beach / Beaches features (T.BCH /
T.BCHS), after nearby identical-name deduplication. Country and region labels
come from GeoNames. Up to 12 alternate names support non-Latin search. Worldwide
records are also deduplicated against nearby matching U.S. names at runtime;
existing IDs and favorites are preserved. Distinct monitoring segments and
alternate names may still produce duplicate-looking beaches. GeoNames data is
CC BY 4.0, attributed in the app, with a per-record source link. Unknown activity
suitability and access are explicit.

Download `allCountries.zip`, `countryInfo.txt` and `admin1CodesASCII.txt` from
https://download.geonames.org/export/dump/ into an external cache, then run
`python3 scripts/build_world_catalogue.py --cache /absolute/cache` from `mobile`.
This streams the archive; no GeoNames account or runtime API key is required.
`world-provenance.json` records input hashes and the snapshot time.


`mobile/src/discover/data/us-beaches.json` is generated from:

- EPA BEACON's public `WQP_Beaches` Beach Lines layer: active, nonhistorical,
  nondormant coastal and Great Lakes records, keyed by EPA beach ID. These are
  geographic records, not a live advisory/closure feed.
- USGS GNIS Domestic Names: current Beach-class records, excluding historical
  names and missing coordinates. These add inland waters and additional named
  beaches. Location names do not verify public access or suitability for swimming.
- The original 14 curated San Diego entries, retaining their IDs and favorites.
  Nearby matching EPA/USGS names are deduplicated against them.

Coverage includes the Atlantic, Pacific, Gulf, Great Lakes, Alaska, Hawaii, Puerto
Rico, U.S. Virgin Islands, Guam, Northern Mariana Islands and American Samoa.
There are records for 50 state/territorial/DC jurisdictions, not every inland
state. An unnamed access point or a beach absent from the official records will
not appear. This is nationwide coverage, not a guarantee that every U.S. beach
or access point has been inventoried. Duplicate-looking records can represent
separate EPA monitoring segments of the same shoreline.

The catalogue works offline after the app loads. Internet is required for map
tiles, forecasts, advisories and city/place lookup. Source coordinates are approximate
feature locations and not access directions. Reported private access is displayed
and excluded from swimming/surfing comparison candidates. Unknown access is
labelled unverified; the user must check local permission and posted restrictions.

`data/provenance.json` contains source URLs, retrieval time, record counts and
SHA-256s of the downloaded inputs. Rebuild the catalogue with:

```sh
python scripts/build_beach_catalogue.py --cache /absolute/path/to/scratch
```

Use an empty cache directory to retrieve a new snapshot. The script paginates the
EPA service, validates coordinates and combines the data reproducibly. Raw
archives are cached outside the source tree and are not included in the app.

## Conditions and comparisons

- Ocean-associated locations: Open-Meteo marine/weather model forecasts for
  wave height/period, sea-surface temperature, wind, air temperature and a
  24-hour marine forecast. Modeled sea level includes tides relative to mean sea
  level and is explicitly not a local tide-gauge reading.
- Known Great Lakes / inland records: weather, plus NWS where covered. Ocean
  forecasts are not requested for known lakes.
- Unclassified waters: a regional ocean forecast is shown only if the returned
  model grid coordinate is within 20 km. Otherwise ocean fields are withheld;
  local weather remains available. Proximity does not verify water type or
  local bathing/surfing suitability; the UI labels the offshore model limitation.
- NWS: active alerts for the U.S. and territories only. International records
  explicitly show that the official feed is unsupported; worldwide forecast
  checks run separately. They never call NWS or claim an official all-clear. Only Actual, noncancelled, nonexpired messages are shown.
  A failed supported feed stays unknown.
- Water quality/closures: links to the relevant official beach-programme lookup;
  the San Diego county link is used only for San Diego records. Other states
  link to EPA's official beach-programme information. International locations
  link to their geographic source and ask users to consult local authorities;
  that source is not represented as a water-quality authority. These changes are NOT
  automatically monitored by this app.

Only the selected beach plus the displayed 12-result page is fetched (maximum
13 locations), with three workers and cached results. Changing the search changes
the batch. Never request forecasts for all thousands of records. Refresh runs on
startup, foreground resume, manually, and every five minutes while active. The
last 150 retrieved location responses are persisted. Failed sources remain
unavailable; total outages preserve cached values with their original timestamp.
Data over 30 minutes old or model times over three hours old is marked outdated.

Swimming comparisons prefer lower modeled waves/wind. Surfing comparisons
prefer waves near 1.2m, longer periods and lower wind. These are transparent
heuristics across the displayed coastal shortlist, not an exhaustive worldwide
ranking or a safety/surf-quality model. Known inland waters and unclassified waters without a nearby ocean grid lack a marine
comparison. International comparisons explicitly indicate absent alert coverage. Source records do not certify that surfing or swimming is permitted.
Severe alerts and missing/stale data lower ranking; proximity breaks ties. Near me
first limits and orders records by distance. No swimmer ability, local rip-current
strength, lifeguard coverage or actual water quality is inferred.

## Map, place lookup and attribution

Leaflet 1.9.4 and OpenStreetMap provide the interactive map, with visible OSM
attribution, normal caching and identifiable native requests. Clustering limits
marker rendering to visible geographic groups. At high zoom, individual beaches
can be selected. Longitude bounds use the smallest enclosing arc, and markers wrap around the map
center so countries such as Fiji can be browsed across the date line.
The searchable list remains available if the map cannot load.

City/place search uses Open-Meteo geocoding / GeoNames worldwide, with country
labels to distinguish similarly named places. Choosing a place searches the local catalogue
within a radius of that location; it does not invent beach records. Device
location is requested only on tapping Near me, stays in memory and is not stored.

## Favorites and alerts

Original favorite IDs remain valid, and national EPA/USGS IDs can be favorited
and checked by the same foreground/background alert service where NWS is supported.
Every favorite, in any country, is checked for AQVARIN forecast alerts.
Official NWS warnings remain an additional source for supported U.S. locations. Preferences,
deduplication keys, condition cache and a bounded 50-notice inbox are on-device.
Removing a favorite or disabling alerts stops its future notifications. Existing
notices remain until expired. Each beach/alert ID/sent-time combination is
notified once, including active notices found on first enabling alerts.

Web checks on opening/resuming and every five minutes while open. Browser
notifications are optional; the inbox works without notification permission.
There is no closed-browser push service. Native also requests a background task
with a minimum 15-minute interval; actual execution is controlled by the phone
and can be delayed or unavailable, especially after force quitting. This is not
guaranteed immediate push delivery.

## Sources

- https://www.epa.gov/beaches/national-list-beaches
- https://beacon.epa.gov/ords/beacon2/r/beacon_apex/beacon2/map-page
- https://www.usgs.gov/us-board-on-geographic-names/download-gnis-data
- https://open-meteo.com/en/docs/marine-weather-api
- https://open-meteo.com/en/docs/geocoding-api
- https://www.weather.gov/documentation/services-web-api

## Validation

Focused tests cover worldwide coordinates and coverage, country/state/name/favorite and
radius filtering, coastal activity comparisons, private access, international geocoding, inland forecast isolation, regional notice links, bounded forecast
fan-out, stale/unknown data, failed sources, alert deduplication and unsubscribe
handling, and safe clustered-map embedding. TypeScript and web/Android/iOS bundle
exports are checked. Browser verification includes worldwide clusters, Australia filtering, Bondi
conditions and explicit international advisory coverage. Native background delivery still
requires physical-device validation on a rebuilt app.

Global source: https://www.geonames.org/ and https://download.geonames.org/export/dump/

## Worldwide forecast alerts

Every catalogue entry can be favorited and monitored, without a country gate.
Open-Meteo hourly weather and available regional ocean models supply a rolling
12-hour window. The UI and optional notifications clearly label these as
AQVARIN forecast alerts, separate from official government warnings:

- Wave height at least 2 m, where ocean coverage is supported.
- Wind at least 35 km/h or gusts at least 50 km/h.
- Thunderstorm weather codes 95, 96 or 99.
- UV index at least 8.

These are product thresholds, not official hazard thresholds, a rip-current
model, a local closure feed or a declaration of safe conditions. Each result
shows its forecast window, source and limitations. Missing / stale model samples
cannot trigger a threshold or establish an all-clear. Known lakes never borrow
an ocean forecast; unclassified waters still require a nearby ocean grid.
Weather checks require at least 11 hourly values per rule within the next 12
hours to report a complete check. Incomplete checks still preserve valid
positive alerts and existing notices. Failure status is shown, including when
only some favorites can be checked.

The same beach/rule/UTC-day is notified once to avoid repeated notifications
while a threshold stays exceeded. A new UTC day can notify again. Notices are
snapshots of the forecast when issued, expire after their last forecasted
exceedance hour, and do not send an all-clear when they expire. Removing a
favorite or pausing alerts stops new notifications. Browser checks require the
app to remain open; native background checks depend on OS scheduling. No cloud
push backend is included. Alert checks visit saved favorites, never all 22,228
locations in the background. Current displayed results show forecast alerts
without requiring the user to enable notifications.

Additional tests exercise international favorite notification delivery,
deduplication, unsubscribe, failed sources, forecast freshness and rule values.
Weather API variables and codes: https://open-meteo.com/en/docs

## Beach photos and traveler briefs

The selected beach loads an online photo, a short overview and nearby travel
listings through Wikimedia's public MediaWiki APIs. This works for any catalogue
entry; source coverage is not guaranteed for every beach. No images are generated
or generic stock beaches substituted.

- Wikipedia: geosearch within 5 km, matching the beach name or an alias against
  article titles and checking article coordinates. English is tried first;
  selected countries also try their local-language Wikipedia. At least 80%
  token agreement is required. Unrelated nearby hotels and aquariums do not
  become the beach article.
- Wikimedia Commons: the matched article's lead image, with its original file
  page, author and reusable license. A named, geotagged Commons search within
  1 km is the fallback. Supported photos are JPEG/PNG/WebP, with CC BY, CC BY-SA,
  CC0 or public-domain metadata. Maps, logos and diagrams are excluded by title.
  Photos are remotely loaded, cropped for display, credited beneath the image,
  and linked to the source and license. Image relevance is a geographic/name
  heuristic and can still be imperfect.
- Wikivoyage: nearby guides within 10 km, using geocoded Eat / See / Do listings
  within 3 km of the beach. The nearest three food listings and up to three
  other sights are shown. Descriptions are plain-text excerpts, attributed
  and linked under CC BY-SA 4.0. They are guide listings, not review rankings,
  popularity claims or verified live opening hours. Distances are straight-line.

No hardcoded restaurant recommendations are fabricated for uncovered locations.
If sources have no matching photo or listings, the beach retains its geographic
summary, shows an explicit unavailable state and offers online photo/dining/map
links. Source errors and image-load failures are visible and retryable. A
photo-source failure does not discard the sourced article or travel listings.

Only the selected beach triggers these lookups, with cancellation on selection
changes. Responses cache on-device for 24 hours (5 minutes for partial errors),
up to 40 beaches, and refresh when revisited after expiry. A manual refresh
control also reloads the travel sources on request. Source failures can
preserve saved content with its original timestamp. This does not download
22,228 photos or fetch traveler information for every map marker at once.
Native image loading and browser CORS depend on the external sources remaining
available. Restroom / picnic / parking amenity badges are removed from the brief.

Primary API references: https://www.mediawiki.org/wiki/API:Geosearch and
https://www.mediawiki.org/wiki/API:Imageinfo
