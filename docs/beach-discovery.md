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
  explicitly show that monitoring is unsupported; they never call NWS or claim
  an all-clear. Only Actual, noncancelled, nonexpired messages are shown.
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
International favorites persist but are not monitored for official alerts. With
only international favorites, the alert service reports this coverage limit. Preferences,
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
