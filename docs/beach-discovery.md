# Beach discovery

The Discover tab adds a San Diego County beach catalogue, interactive map,
activity comparisons, location-based distance filtering, saved favorites and
National Weather Service advisory notifications. Discovery runs independently
of the local Python analysis server. Existing upload/live analysis is unchanged.

## Run and verify

From `mobile`:

```sh
npm ci
npm run typecheck
npm run test:discover
npm run web
```

Native applications must be rebuilt (`npm run android` / `npm run ios`) because
this feature adds Expo Location, Notifications, Background Task, Task Manager,
and React Native WebView. The existing Pixel APK does not contain these changes.
Native notification permission and background scheduling still need physical
Android/iOS testing; successful JavaScript exports do not establish device behavior.

## Data and scope

- Catalogue: 14 San Diego County beaches, with visitor-information source links.
  The catalogue is curated, not a worldwide beach search service. Amenities are
  visitor information, not guarantees of opening hours or lifeguard coverage.
- Map: Leaflet 1.9.4 (BSD-2-Clause) and OpenStreetMap tiles, loaded over HTTPS.
  OpenStreetMap attribution is visible. Internet is required for map assets.
  If the map cannot load, the searchable beach list remains usable.
- Marine/weather: Open-Meteo Marine and Weather APIs (Open-Meteo/DWD attribution
  shown in beach details). Data is modeled, not a beach sensor measurement.
  Wave height/period, sea-surface temperature, wind, air temperature, and a
  24-hour forecast are included. Modeled sea level includes tides relative to
  mean sea level; it is explicitly not a local tide-gauge reading.
- Advisories: NWS active alerts at each beach coordinate. Only Actual,
  non-cancelled, non-expired messages are used. Failed feeds remain unknown.
- Water quality/closures: link to the County Beach & Bay Water Quality Program,
  https://www.sdbeachinfo.com/. This version does NOT fetch or notify about
  county bacterial-water-quality or closure changes. NWS alerts are distinct.
- Source docs: https://open-meteo.com/en/docs/marine-weather-api and
  https://www.weather.gov/documentation/services-web-api.

Conditions refresh on startup, foreground resume, manual request, and every
five minutes while active. The last retrieved data is saved locally. Data more
than 30 minutes old, or marine model timestamps more than three hours old, is
marked outdated; incomplete/stale data is demoted in activity comparisons.
Partial failures preserve other successfully returned fields. A total outage
preserves cached data and its original timestamp.

Swimming comparisons prefer lower modeled waves/wind; surfing comparisons
prefer waves near 1.2m, longer periods, and lower wind. This is a transparent
comparison heuristic, not a surf-quality model or safety assessment. Severe
alerts demote a beach. Distance breaks ties; the Near me radius filters the
catalogue before ranking. Skill, local currents, local breaks, water quality,
and lifeguard decisions are not inferred.

## Favorites and alerts

Favorites, subscriptions, deduplication keys, condition cache and a bounded
50-notice inbox are stored with AsyncStorage on the device. Disabling alerts or
removing a favorite stops future notifications for that subscription. Existing
inbox notices remain until expired. Each beach/alert ID/sent-time combination
is delivered once, including active notices found when first enabling alerts.

- Web: check on opening/resuming and every five minutes while open. Browser
  notifications are optional; in-app inbox works without notification permission.
  There is no browser push service and no closed-browser delivery.
- Native: same foreground checks, plus an OS-scheduled background task requested
  at a minimum interval of 15 minutes. Scheduling and delivery can be delayed
  or unavailable, especially after force quitting. This is not guaranteed instant
  push. The UI reports background availability and permission limitations.

Location is requested only after tapping Near me, used locally to calculate
straight-line distance, and not persisted. Denial leaves city/name search usable.
No account, API key, continuous location tracking, or new hosted backend is required.

## Validation

`npm run test:discover` covers catalogue coordinates/uniqueness, distance,
expired/test/cancelled alerts, activity ordering, stale/unknown data, partial
source outages, notification deduplication and unsubscribe handling.

TypeScript and Expo Android/iOS/web bundle exports passed during implementation.
Browser checks confirmed live source data, city filtering, swimming filtering,
map rendering and favorite persistence after reload. Device background delivery
and notification permissions require verification on a rebuilt app.
