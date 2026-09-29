# Expedia Lite — Assignment 2 Part 1 Design

## Scope

Assignment 2 Part 1 adds a backend-mediated nearby-hotel demonstration to the
existing Expedia Lite ZIP lookup. The user enters a five-digit ZIP as a
string. The backend resolves the ZIP, uses its coordinates as the search
center, and requests hotel places within a 5 km radius. The Vue view displays
only fields returned by the provider; it does not claim price, availability,
rating, or booking information.

## Research and source links

- [Geoapify Forward Geocoding API](https://apidocs.geoapify.com/docs/geocoding/forward-geocoding/)
  documents postcode lookup, the `type`, `filter`, and `format` parameters,
  and the JSON response used for the ZIP center.
- [Geoapify Places API](https://apidocs.geoapify.com/docs/places/) documents
  category and circle searches for nearby places.
- [Leaflet reference](https://leafletjs.com/reference.html) documents the map,
  marker, layer, popup, and view APIs used by the frontend.
- [OpenStreetMap attribution](https://www.openstreetmap.org/copyright) is
  visible in the Leaflet tile-layer attribution.

The useful interaction observed for this project was an explicit location
search flow with a labeled input, a submit button, visible loading feedback,
and a distinct result/error area. The source was the running local Expedia
Lite UI at [http://127.0.0.1:5174/](http://127.0.0.1:5174/), observed on
2026-09-29. The early mockup link is **Not verified**: no separate mockup URL
is recorded in the repository or handoff history.

## Interaction and response contract

The ZIP form trims surrounding whitespace, preserves leading zeros, validates
exactly five ASCII digits, and calls the local relative endpoint
`/api/hotels/nearby?zip_code=<zip>`. The Geoapify key stays in the backend;
Vue never calls Geoapify directly.

The route returns a JSON object with `zip_code`, a `center` object containing
the resolved `latitude` and `longitude`, and a `results` array. Each result
contains the provider's `place_id`, `name`, `latitude`, and `longitude`, plus
`address` and/or `locality` only when those fields are present in the provider
response.

`address` and `locality` are included only when supplied by the provider.
`place_id` is the stable identity used to deduplicate results and synchronize
the list with map markers. The search circle is always 5 km (`5000` metres)
around the resolved ZIP coordinates.

The view exposes initial, loading, invalid ZIP, unresolved ZIP, no nearby
hotels, provider/network failure, incomplete provider data, and success
states. A new search clears the previous results, markers, and selection.
List selection opens and highlights the matching marker; marker selection
highlights the matching list item. Keyboard activation and visible focus are
preserved.

## MVC responsibilities

- **Vue (View):** owns form and presentation state, calls the local JSON API,
  renders the location, provider hotel list, Leaflet map, and safe messages.
- **FastAPI (boundary/controller adapter):** validates the query parameter,
  delegates to Python controllers, preserves existing routes, and maps
  invalid input, unresolved ZIPs, no results, incomplete data, and provider
  failures to safe HTTP responses.
- **Python controllers (business/data access):** keep Geoapify geocoding and
  Places request logic backend-only, apply finite timeouts, validate response
  fields and coordinates, enforce the 5 km circle, and remove credential or
  raw-provider details from returned errors.
- **SQLite MVC flow:** the existing database controllers remain responsible
  for Assignment 1 Part 2 records and booking workflows; the nearby-provider
  demonstration does not write to SQLite.

## Limitations and next step

Geoapify Places results are provider observations only. They do not prove a
hotel has rooms, a price, availability, or a reservation. The map also
depends on network-loaded OpenStreetMap tiles. Automated tests cover success,
empty results, provider failure, unresolved ZIP, invalid input, incomplete
provider data, and safe route mapping. Live browser verification covered ZIPs
`16802`, `10001`, and leading-zero `00501`; a live no-results ZIP and a live
provider/network outage were not reproduced without changing or stopping
services.

The next task is **Assignment 2 Part 2: shortlist**. No shortlist behavior is
included in this Part 1 flow.
