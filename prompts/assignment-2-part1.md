# Assignment 2 Part 1 — nearby hotels and map

## Development brief

Extend the existing Expedia Lite ZIP lookup with a backend-only Geoapify
Places search. Resolve a validated five-digit ZIP first, then search for
hotel places within a 5 km circle centered on the returned latitude and
longitude. Keep the Geoapify key and provider requests in Python; Vue may
call only the local FastAPI endpoint.

The backend contract is:

```text
GET /api/hotels/nearby?zip_code=<five-digit-zip>
```

The sanitized response contains the requested ZIP, the search center, and
provider results with `place_id`, `name`, optional `address` and `locality`,
`latitude`, and `longitude`. It must not manufacture price, rating,
availability, or booking fields. Invalid ZIP, unresolved ZIP, no results,
incomplete provider data, and provider/network failure are separate safe
outcomes.

The Vue view must retain the existing hotel-name search and ZIP input, show
the returned hotel list and Leaflet map, use visible OpenStreetMap
attribution, deduplicate by `place_id`, and synchronize list selection with
the corresponding marker. A new ZIP search clears stale results and
selection. Initial, loading, invalid, unresolved, no-results,
provider/network-failure, incomplete-data, and success states remain
visibly distinct. No shortlist, map-based booking, or hotel availability
claim is included.

## Verification record

Observation date: **2026-09-29**.

- Backend mocked coverage: 23 tests passed, including ZIP validation,
  geocoding, nearby-hotel success, no results, provider failure, unresolved
  ZIP, incomplete provider data, and safe route mappings.
- Frontend checks: `npm run lint` and `npm run build` passed.
- Browser URL: [http://127.0.0.1:5174/](http://127.0.0.1:5174/).
- Tested ZIPs: `16802` and `10001` returned successful provider results;
  `00501` remained a string and produced the observed unresolved state.
- Browser interaction evidence: loading cleared old results; the successful
  `10001` view showed 20 cards and 20 markers with visible attribution;
  list-to-map selection opened and highlighted the matching marker, and
  marker-to-list selection highlighted the matching list hotel.
- A live no-nearby ZIP and a live provider/network outage were not reproduced
  without changing or stopping services; mocked coverage verifies those
  branches.

## Sources and limitations

- [Geoapify Forward Geocoding API](https://apidocs.geoapify.com/docs/geocoding/forward-geocoding/)
- [Geoapify Places API](https://apidocs.geoapify.com/docs/places/)
- [Leaflet reference](https://leafletjs.com/reference.html)
- [OpenStreetMap copyright and attribution](https://www.openstreetmap.org/copyright)

No separate early mockup URL is recorded in the repository, so an early
mockup link is **Not verified**. The next task after this prompt is
**Assignment 2 Part 2: shortlist**.
