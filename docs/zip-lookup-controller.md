# ZIP lookup controller contract

`LocationController.lookup_demo_postcode()` is a backend-only controller function for the fixed demonstration input `16802`. There is no FastAPI route or Vue integration yet.

The controller reads `GEOAPIFY_API_KEY` through `backend/app/config.py` and makes the Geoapify forward-geocoding request only from Python. It uses a finite 10-second timeout and sends the fixed postcode with `type=postcode`, `filter=countrycode:us`, and `format=json`.

On a validated match, it returns only the postcode, country code, finite latitude and longitude, and (when supplied) locality:

```json
{
  "postcode": "16802",
  "country_code": "us",
  "latitude": "number",
  "longitude": "number",
  "locality": "string"
}
```

`locality` is omitted when the provider does not supply a non-blank city or locality. A result is accepted only when it reports postcode `16802`, country code `us`, and finite, in-range latitude and longitude. This response is separate from the `Hotel` model and does not include a price.

`ZipLookupConfigurationError` means the backend key is not configured. `ZipLookupUnresolvedError` means the provider returned successfully but no result passed validation. `ZipLookupProviderError` means the request failed or the provider response was malformed. Neither error exposes the key, a credential-bearing URL, or provider exception text.
