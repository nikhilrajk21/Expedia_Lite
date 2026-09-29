<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const hotelName = ref('')
const results = ref([])
const hasSearched = ref(false)
const isLoading = ref(false)
const errorMessage = ref('')
const selectedTripId = ref('')
const activeSort = ref('recommended')
const plannedNights = ref(2)
const bookings = ref([])
const bookingForm = ref({ userId: 'U001', tripId: 'T001', bookedOn: '2026-09-10', isTest: false })
const bookingLoading = ref(false)
const bookingMessage = ref('')
const bookingError = ref('')
const zipCode = ref('')
const zipLocation = ref(null)
const zipLoading = ref(false)
const zipValidationMessage = ref('')
const zipError = ref('')
const nearbyState = ref('initial')
const nearbyHotels = ref([])
const nearbyMapElement = ref(null)
const nearbyMap = ref(null)
const nearbyMarkerLayer = ref(null)
const selectedNearbyPlaceId = ref('')
const nearbyMarkersByPlaceId = new Map()

const allStays = computed(() => results.value.flatMap((hotel) => hotel.available_stays.map((stay) => ({
  ...stay,
  hotelId: hotel.hotel_id,
  hotelName: hotel.hotel_name,
  city: hotel.city,
  state: hotel.state,
  nightlyRate: Number(hotel.nightly_rate_usd),
}))))

const displayedStays = computed(() => {
  const stays = [...allStays.value]
  if (activeSort.value === 'lowest') return stays.sort((a, b) => a.nightlyRate - b.nightlyRate)
  return stays.sort((a, b) => a.trip_name.localeCompare(b.trip_name))
})

const selectedStay = computed(() => allStays.value.find((stay) => stay.trip_id === selectedTripId.value))

const availabilityDays = computed(() => {
  if (allStays.value.length === 0) return []
  const firstDate = [...allStays.value].sort((a, b) => a.check_in.localeCompare(b.check_in))[0].check_in
  const start = new Date(firstDate + 'T00:00:00')
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(start)
    date.setDate(start.getDate() + index)
    const dateKey = date.toISOString().slice(0, 10)
    return {
      dateKey,
      weekday: new Intl.DateTimeFormat('en-US', { weekday: 'short' }).format(date),
      day: new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(date),
      stays: allStays.value.filter((stay) => stay.check_in === dateKey),
    }
  })
})

const chartMaxRate = computed(() => Math.max(...allStays.value.map((stay) => stay.nightlyRate), 1))

async function requestJson(url, options) {
  const response = await fetch(url, options)
  const data = await response.json()
  if (!response.ok) {
    const error = new Error(data.detail ?? 'Request failed with status ' + response.status)
    error.status = response.status
    throw error
  }
  return data
}

async function searchHotels() {
  hasSearched.value = true
  isLoading.value = true
  errorMessage.value = ''
  selectedTripId.value = ''
  results.value = []
  try {
    const data = await requestJson('/api/hotels/search?name=' + encodeURIComponent(hotelName.value))
    results.value = data.results
  } catch (error) {
    errorMessage.value = error.message ?? 'Unable to reach the hotel search service.'
  } finally {
    isLoading.value = false
  }
}

function validateZipCode(value) {
  if (!value) return 'Enter a five-digit U.S. ZIP code.'
  if (value.length < 5) return 'ZIP codes must contain five digits.'
  if (value.length > 5) return 'ZIP codes must contain exactly five digits.'
  if (!/^\d{5}$/.test(value)) return 'Use five digits only; do not include letters or spaces.'
  return ''
}

function isValidCoordinate(value, minimum, maximum) {
  return typeof value === 'number' && Number.isFinite(value) && value >= minimum && value <= maximum
}

function validateNearbyHotels(hotels) {
  if (!Array.isArray(hotels)) return { valid: false, hotels: [] }
  const seenPlaceIds = new Set()
  const validHotels = []
  for (const hotel of hotels) {
    const hasRequiredFields = hotel
      && typeof hotel.place_id === 'string'
      && hotel.place_id.trim()
      && typeof hotel.name === 'string'
      && hotel.name.trim()
      && isValidCoordinate(hotel.latitude, -90, 90)
      && isValidCoordinate(hotel.longitude, -180, 180)
    if (!hasRequiredFields) return { valid: false, hotels: [] }
    if (seenPlaceIds.has(hotel.place_id)) continue
    seenPlaceIds.add(hotel.place_id)
    validHotels.push(hotel)
  }
  return { valid: true, hotels: validHotels }
}

function destroyNearbyMap() {
  if (nearbyMap.value) {
    nearbyMap.value.stop()
    nearbyMap.value.remove()
  }
  nearbyMap.value = null
  nearbyMarkerLayer.value = null
  nearbyMarkersByPlaceId.clear()
  selectedNearbyPlaceId.value = ''
}

function popupContent(hotel) {
  const content = document.createElement('div')
  const name = document.createElement('strong')
  name.textContent = hotel.name
  content.append(name)
  const address = hotel.address || hotel.locality
  if (address) {
    const detail = document.createElement('div')
    detail.textContent = address
    content.append(detail)
  }
  return content
}

function hotelMarkerIcon(selected) {
  return L.divIcon({
    className: 'nearby-marker-icon',
    html: '<span class="nearby-marker-dot' + (selected ? ' selected' : '') + '" aria-hidden="true"></span>',
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -12],
  })
}

function updateNearbyMarkerStyles() {
  nearbyMarkersByPlaceId.forEach((marker, placeId) => {
    const selected = placeId === selectedNearbyPlaceId.value
    marker.setIcon(hotelMarkerIcon(selected))
    marker.setZIndexOffset(selected ? 1000 : 0)
  })
}

function highlightNearbyHotel(placeId) {
  selectedNearbyPlaceId.value = placeId
  updateNearbyMarkerStyles()
}

function selectNearbyHotel(placeId) {
  highlightNearbyHotel(placeId)
  const marker = nearbyMarkersByPlaceId.get(placeId)
  if (!marker || !nearbyMap.value) return
  marker.openPopup()
  nearbyMap.value.panTo(marker.getLatLng())
}

function renderNearbyMap() {
  const location = zipLocation.value
  if (!nearbyMapElement.value || !location) return
  if (!isValidCoordinate(location.latitude, -90, 90) || !isValidCoordinate(location.longitude, -180, 180)) return

  const center = [location.latitude, location.longitude]
  if (!nearbyMap.value) {
    nearbyMap.value = L.map(nearbyMapElement.value, { scrollWheelZoom: false })
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(nearbyMap.value)
    nearbyMarkerLayer.value = L.layerGroup().addTo(nearbyMap.value)
  }

  nearbyMap.value.setView(center, 13)
  nearbyMarkerLayer.value.clearLayers()
  nearbyMarkersByPlaceId.clear()
  const bounds = L.latLngBounds([center])
  L.circleMarker(center, {
    color: '#1769e8',
    fillColor: '#1769e8',
    fillOpacity: 0.2,
    radius: 10,
  }).bindPopup('ZIP ' + location.postcode).addTo(nearbyMarkerLayer.value)

  let hotelMarkerCount = 0
  nearbyHotels.value.forEach((hotel) => {
    if (!isValidCoordinate(hotel.latitude, -90, 90) || !isValidCoordinate(hotel.longitude, -180, 180)) return
    const coordinates = [hotel.latitude, hotel.longitude]
    const marker = L.marker(coordinates, {
      icon: hotelMarkerIcon(false),
      title: hotel.name,
    })
      .bindPopup(popupContent(hotel))
      .on('click', () => selectNearbyHotel(hotel.place_id))
      .on('popupopen', () => highlightNearbyHotel(hotel.place_id))
      .addTo(nearbyMarkerLayer.value)
    nearbyMarkersByPlaceId.set(hotel.place_id, marker)
    bounds.extend(coordinates)
    hotelMarkerCount += 1
  })

  if (hotelMarkerCount > 0) nearbyMap.value.fitBounds(bounds, { padding: [24, 24], maxZoom: 14 })
  nearbyMap.value.invalidateSize()
}

async function lookupZip() {
  nearbyState.value = 'loading'
  zipLocation.value = null
  nearbyHotels.value = []
  destroyNearbyMap()
  zipValidationMessage.value = ''
  zipError.value = ''

  const validatedZip = zipCode.value.trim()
  zipCode.value = validatedZip
  const validationMessage = validateZipCode(validatedZip)
  if (validationMessage) {
    nearbyState.value = 'invalid'
    zipValidationMessage.value = validationMessage
    return
  }

  zipLoading.value = true
  try {
    const data = await requestJson('/api/hotels/nearby?zip_code=' + encodeURIComponent(validatedZip))
    if (!data || typeof data.zip_code !== 'string' || !data.center
      || !isValidCoordinate(data.center.latitude, -90, 90)
      || !isValidCoordinate(data.center.longitude, -180, 180)) {
      nearbyState.value = 'invalid-provider-data'
      zipError.value = 'The provider returned incomplete location data, so no results were shown.'
      return
    }
    const normalizedResults = validateNearbyHotels(data.results)
    if (!normalizedResults.valid) {
      nearbyState.value = 'invalid-provider-data'
      zipError.value = 'The provider returned incomplete hotel data, so no results were shown.'
      return
    }
    if (normalizedResults.hotels.length === 0) {
      nearbyState.value = 'no-results'
      zipError.value = 'No nearby hotels were found for that ZIP code.'
      return
    }
    zipLocation.value = {
      postcode: data.zip_code,
      latitude: data.center.latitude,
      longitude: data.center.longitude,
    }
    nearbyHotels.value = normalizedResults.hotels
    nearbyState.value = 'success'
    await nextTick()
    renderNearbyMap()
  } catch (error) {
    if (error.status === 400) {
      nearbyState.value = 'invalid'
      zipError.value = 'Use exactly five ASCII digits for the ZIP code.'
    } else if (error.status === 404) {
      nearbyState.value = error.message.includes('No hotels') ? 'no-results' : 'unresolved'
      zipError.value = error.message.includes('No hotels')
        ? 'No nearby hotels were found for that ZIP code.'
        : 'That ZIP code could not be resolved.'
    } else if (error.status === 502) {
      nearbyState.value = error.message.includes('incomplete') ? 'invalid-provider-data' : 'provider-error'
      zipError.value = error.message.includes('incomplete')
        ? 'The provider returned incomplete hotel data, so no results were shown.'
        : 'The nearby hotel provider is temporarily unavailable.'
    } else if (error.status === 503) {
      nearbyState.value = 'provider-error'
      zipError.value = 'The nearby hotel service is not configured.'
    } else {
      nearbyState.value = 'network-error'
      zipError.value = 'The nearby hotel service could not be reached. Please try again.'
    }
  } finally {
    zipLoading.value = false
  }
}

function selectStay(stay) {
  selectedTripId.value = stay.trip_id
  bookingForm.value.tripId = stay.trip_id
  bookingMessage.value = stay.trip_name + ' selected. Complete the booking below.'
  document.getElementById('bookings')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function adjustNights(change) {
  plannedNights.value = Math.min(14, Math.max(1, plannedNights.value + change))
}

async function loadBookings() {
  try {
    const data = await requestJson('/api/bookings')
    bookings.value = data.bookings
  } catch (error) {
    bookingError.value = error.message ?? 'Unable to load booking history.'
  }
}

async function createBooking() {
  bookingLoading.value = true
  bookingMessage.value = ''
  bookingError.value = ''
  try {
    const data = await requestJson('/api/bookings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: bookingForm.value.userId,
        trip_id: bookingForm.value.tripId,
        booked_on: bookingForm.value.bookedOn,
        is_test: bookingForm.value.isTest,
      }),
    })
    bookingMessage.value = 'Booking ' + data.booking.booking_id + ' was created.'
    await loadBookings()
  } catch (error) {
    bookingError.value = error.message ?? 'Unable to create the booking.'
  } finally {
    bookingLoading.value = false
  }
}

async function cancelBooking(bookingId) {
  bookingMessage.value = ''
  bookingError.value = ''
  try {
    const data = await requestJson('/api/bookings/' + bookingId, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'cancelled' }),
    })
    bookingMessage.value = 'Booking ' + data.booking.booking_id + ' was cancelled and kept in history.'
    await loadBookings()
  } catch (error) {
    bookingError.value = error.message ?? 'Unable to cancel booking ' + bookingId + '.'
  }
}

async function deleteBooking(bookingId) {
  bookingMessage.value = ''
  bookingError.value = ''
  try {
    const data = await requestJson('/api/bookings/' + bookingId, { method: 'DELETE' })
    bookingMessage.value = 'Test booking ' + data.deleted_booking_id + ' was deleted.'
    await loadBookings()
  } catch (error) {
    bookingError.value = error.message ?? 'Unable to delete booking ' + bookingId + '.'
  }
}

onMounted(loadBookings)
onBeforeUnmount(destroyNearbyMap)
</script>

<template>
  <main>
    <section
      class="hero"
      aria-labelledby="page-title"
    >
      <nav
        class="topbar"
        aria-label="Primary navigation"
      >
        <a
          class="brand"
          href="#top"
        ><span class="brand-mark">↗</span> Expedia Lite</a>
        <div class="nav-links">
          <a href="#search">Shop stays</a><a href="#bookings">Trips</a><button
            type="button"
            class="icon-button"
            aria-label="Messages"
          >
            ▢
          </button><button
            type="button"
            class="icon-button"
            aria-label="Account"
          >
            ◉
          </button>
        </div>
      </nav>
      <div
        id="top"
        class="hero-copy"
      >
        <p class="eyebrow light">
          YOUR NEXT STAY STARTS HERE
        </p>
        <h1 id="page-title">
          A better way to find your next place.
        </h1>
        <p>Search your available stays, explore their real dates and rates, then book from one simple trip desk.</p>
      </div>
      <div
        id="search"
        class="search-shell"
      >
        <div
          class="travel-tabs"
          role="tablist"
          aria-label="Travel categories"
        >
          <button
            class="travel-tab active"
            type="button"
            role="tab"
            aria-selected="true"
          >
            <span aria-hidden="true">⌂</span> Stays
          </button>
          <span
            class="travel-tab unavailable"
            aria-label="Flights are not available"
          ><span aria-hidden="true">✈</span> Flights</span>
          <span
            class="travel-tab unavailable"
            aria-label="Cars are not available"
          ><span aria-hidden="true">▣</span> Cars</span>
          <span
            class="travel-tab unavailable"
            aria-label="Packages are not available"
          ><span aria-hidden="true">✦</span> Packages</span>
          <span
            class="travel-tab unavailable"
            aria-label="Things to do are not available"
          ><span aria-hidden="true">◒</span> Things to do</span>
        </div>
        <form
          class="search-form"
          @submit.prevent="searchHotels"
        >
          <label
            class="search-field destination"
            for="hotel-name"
          >
            <span aria-hidden="true">⌖</span>
            <span><small>Where to?</small><input
              id="hotel-name"
              v-model="hotelName"
              type="search"
              placeholder="Search a hotel name"
            ></span>
          </label>
          <div class="search-field">
            <span aria-hidden="true">▣</span><span><small>Dates</small><strong>See dates after searching</strong></span>
          </div>
          <div class="search-field">
            <span aria-hidden="true">♙</span><span><small>Travelers</small><strong>Use your ID to book</strong></span>
          </div>
          <button
            class="search-button"
            type="submit"
            :disabled="isLoading"
          >
            {{ isLoading ? 'Searching…' : 'Search' }}
          </button>
        </form>
        <section
          class="zip-lookup-panel"
          :data-nearby-state="nearbyState"
          aria-labelledby="zip-lookup-title"
        >
          <div class="zip-lookup-copy">
            <p class="eyebrow">
              LOCATION LOOKUP
            </p>
            <h2 id="zip-lookup-title">
              Find a place by ZIP code
            </h2>
            <p>Check a U.S. ZIP code before planning your stay.</p>
          </div>
          <form
            class="zip-form"
            @submit.prevent="lookupZip"
          >
            <label for="zip-code">U.S. ZIP code<input
              id="zip-code"
              v-model="zipCode"
              type="text"
              inputmode="numeric"
              autocomplete="postal-code"
              aria-describedby="zip-help"
              placeholder="e.g. 16802"
            ></label>
            <button
              class="search-button"
              type="submit"
              :disabled="zipLoading"
            >
              {{ zipLoading ? 'Looking up…' : 'Look up ZIP' }}
            </button>
          </form>
          <p
            id="zip-help"
            class="zip-help"
          >
            Enter five digits. Leading zeros are preserved.
          </p>
          <p
            v-if="nearbyState === 'initial'"
            class="notice"
            role="status"
          >
            Enter a five-digit ZIP code to find nearby hotels.
          </p>
          <p
            v-else-if="zipLoading"
            class="notice"
            role="status"
            aria-live="polite"
          >
            Looking up ZIP…
          </p>
          <p
            v-else-if="zipValidationMessage"
            class="notice error"
            role="alert"
          >
            {{ zipValidationMessage }}
          </p>
          <p
            v-else-if="zipError"
            class="notice error"
            role="alert"
          >
            {{ zipError }}
          </p>
          <dl
            v-if="zipLocation"
            class="zip-location-result"
            aria-label="ZIP location result"
          >
            <div>
              <dt>Postcode</dt><dd>{{ zipLocation.postcode }}</dd>
            </div>
            <div v-if="zipLocation.locality">
              <dt>Locality</dt><dd>{{ zipLocation.locality }}</dd>
            </div>
            <div v-if="zipLocation.country_code">
              <dt>Country code</dt><dd>{{ zipLocation.country_code }}</dd>
            </div>
            <div>
              <dt>Latitude</dt><dd>{{ zipLocation.latitude }}</dd>
            </div>
            <div>
              <dt>Longitude</dt><dd>{{ zipLocation.longitude }}</dd>
            </div>
          </dl>
          <section
            v-if="zipLocation"
            class="nearby-results"
            aria-labelledby="nearby-results-title"
          >
            <div class="nearby-results-heading">
              <div>
                <p class="eyebrow">
                  NEARBY HOTELS
                </p>
                <h2 id="nearby-results-title">
                  Hotels near {{ zipLocation.postcode }}
                </h2>
              </div>
              <span>{{ nearbyHotels.length }} provider result{{ nearbyHotels.length === 1 ? '' : 's' }}</span>
            </div>
            <div class="nearby-results-layout">
              <div
                ref="nearbyMapElement"
                class="nearby-map"
                role="region"
                aria-label="Map of hotels near the ZIP code"
                tabindex="0"
              />
              <div class="nearby-hotel-list">
                <article
                  v-for="hotel in nearbyHotels"
                  :key="hotel.place_id"
                  class="nearby-hotel"
                  :class="{ selected: selectedNearbyPlaceId === hotel.place_id }"
                  role="button"
                  tabindex="0"
                  :aria-pressed="selectedNearbyPlaceId === hotel.place_id"
                  @click="selectNearbyHotel(hotel.place_id)"
                  @keydown.enter.prevent="selectNearbyHotel(hotel.place_id)"
                  @keydown.space.prevent="selectNearbyHotel(hotel.place_id)"
                >
                  <h3>{{ hotel.name }}</h3>
                  <p v-if="hotel.address">
                    {{ hotel.address }}
                  </p>
                  <p v-else-if="hotel.locality">
                    {{ hotel.locality }}
                  </p>
                  <dl class="nearby-hotel-fields">
                    <div v-if="hotel.locality && hotel.address">
                      <dt>Locality</dt><dd>{{ hotel.locality }}</dd>
                    </div>
                    <div>
                      <dt>Place ID</dt><dd>{{ hotel.place_id }}</dd>
                    </div>
                    <div>
                      <dt>Coordinates</dt><dd>{{ hotel.latitude }}, {{ hotel.longitude }}</dd>
                    </div>
                  </dl>
                </article>
              </div>
            </div>
          </section>
        </section>
        <p
          v-if="errorMessage"
          class="notice error"
          role="alert"
        >
          {{ errorMessage }}
        </p>
        <p
          v-else-if="hasSearched && !isLoading && results.length === 0"
          class="notice"
          role="status"
        >
          No hotels matched your search. Try a supplied hotel name.
        </p>
      </div>
    </section>

    <section
      v-if="results.length"
      class="results-page"
      aria-labelledby="results-title"
    >
      <div class="search-summary">
        <div>
          <p class="eyebrow">
            STAY SEARCH
          </p><h2 id="results-title">
            Stays matching “{{ hotelName }}”
          </h2>
        </div>
        <span>{{ allStays.length }} available option{{ allStays.length === 1 ? '' : 's' }}</span>
      </div>
      <div
        class="filter-row"
        aria-label="Stay filters"
      >
        <button
          class="filter-button selected"
          type="button"
        >
          All stays
        </button>
        <button
          class="filter-button"
          type="button"
        >
          Dates
        </button>
        <button
          class="filter-button"
          type="button"
        >
          Price
        </button>
        <button
          class="filter-button"
          type="button"
        >
          Location
        </button>
      </div>
      <div
        class="sort-tabs"
        role="tablist"
        aria-label="Sort stay results"
      >
        <button
          :class="{ active: activeSort === 'recommended' }"
          type="button"
          @click="activeSort = 'recommended'"
        >
          <strong>Recommended</strong><span>by stay name</span>
        </button>
        <button
          :class="{ active: activeSort === 'lowest' }"
          type="button"
          @click="activeSort = 'lowest'"
        >
          <strong>Lowest rate</strong><span>per night</span>
        </button>
      </div>
      <div class="result-layout">
        <div class="stay-list">
          <article
            v-for="stay in displayedStays"
            :key="stay.trip_id"
            class="stay-result"
          >
            <div
              class="result-art"
              aria-hidden="true"
            >
              {{ stay.city.slice(0, 1) }}
            </div>
            <div class="result-details">
              <p>{{ stay.city }}, {{ stay.state }}</p>
              <h3>{{ stay.hotelName }}</h3>
              <span class="trip-name">{{ stay.trip_name }}</span>
              <div class="result-meta">
                <span>{{ stay.check_in }} → {{ stay.check_out }}</span><span>Trip ID {{ stay.trip_id }}</span>
              </div>
            </div>
            <div class="result-price">
              <strong>USD {{ stay.nightlyRate }}</strong><span>per night</span><button
                type="button"
                @click="selectStay(stay)"
              >
                Select stay
              </button>
            </div>
          </article>
        </div>
        <aside
          class="date-grid-card"
          aria-labelledby="date-grid-title"
        >
          <div class="grid-heading">
            <div>
              <p class="eyebrow light">
                DATE VIEW
              </p><h3 id="date-grid-title">
                Available check-ins
              </h3>
            </div><span>Actual stay data</span>
          </div>
          <div
            class="date-grid"
            role="grid"
            aria-label="Available stay check-in dates"
          >
            <div
              v-for="day in availabilityDays"
              :key="day.dateKey"
              class="date-cell"
              role="gridcell"
            >
              <p><small>{{ day.weekday }}</small>{{ day.day }}</p>
              <button
                v-for="stay in day.stays"
                :key="stay.trip_id"
                class="date-stay"
                :class="{ selected: selectedTripId === stay.trip_id }"
                type="button"
                @click="selectStay(stay)"
              >
                <span>{{ stay.hotelName }}</span><strong>USD {{ stay.nightlyRate }}</strong>
              </button>
              <span
                v-if="day.stays.length === 0"
                class="no-options"
              >No check-ins</span>
            </div>
          </div>
        </aside>
      </div>

      <section
        class="rate-panel"
        aria-labelledby="rate-title"
      >
        <div class="rate-heading">
          <div>
            <p class="eyebrow light">
              RATE GRAPH
            </p><h3 id="rate-title">
              Compare nightly rates
            </h3>
          </div>
          <div
            class="nights-control"
            aria-label="Planning stay length"
          >
            <button
              type="button"
              aria-label="Reduce stay by one night"
              @click="adjustNights(-1)"
            >
              −
            </button><strong>{{ plannedNights }}-night plan</strong><button
              type="button"
              aria-label="Extend stay by one night"
              @click="adjustNights(1)"
            >
              +
            </button>
          </div>
        </div>
        <p class="rate-note">
          Bars use the nightly rates returned by the current hotel search. Planning length does not change the supplied stay records.
        </p>
        <div
          class="bar-chart"
          role="img"
          aria-label="Nightly rate comparison"
        >
          <div
            v-for="stay in displayedStays"
            :key="stay.trip_id"
            class="bar-column"
          >
            <span class="bar-value">USD {{ stay.nightlyRate }}</span>
            <div class="bar-track">
              <div
                class="bar"
                :style="{ height: (stay.nightlyRate / chartMaxRate * 100) + '%' }"
              />
            </div>
            <small>{{ stay.trip_id }}</small>
          </div>
        </div>
        <p
          v-if="selectedStay"
          class="selected-note"
          role="status"
        >
          <strong>{{ selectedStay.hotelName }}</strong> is selected for booking: {{ selectedStay.check_in }} to {{ selectedStay.check_out }}.
        </p>
      </section>
    </section>
    <section
      id="bookings"
      class="booking-section"
      aria-labelledby="booking-title"
    >
      <div class="booking-heading">
        <div>
          <p class="eyebrow">
            YOUR TRIPS
          </p><h2 id="booking-title">
            Booking desk
          </h2>
        </div><p>Create, cancel, or delete test bookings using the SQLite-backed API.</p>
      </div>
      <div class="booking-layout">
        <form
          class="booking-form"
          @submit.prevent="createBooking"
        >
          <h3>Make a booking</h3>
          <p>Choose a search result above to fill the Stay ID, then use a valid traveler ID.</p>
          <label for="booking-user-id">Traveler ID<input
            id="booking-user-id"
            v-model.trim="bookingForm.userId"
            required
          ></label>
          <label for="booking-trip-id">Stay ID<input
            id="booking-trip-id"
            v-model.trim="bookingForm.tripId"
            required
          ></label>
          <label for="booking-date">Booked on<input
            id="booking-date"
            v-model="bookingForm.bookedOn"
            type="date"
            required
          ></label>
          <label
            class="checkbox-label"
            for="test-booking"
          ><input
            id="test-booking"
            v-model="bookingForm.isTest"
            type="checkbox"
          > Test booking (can be deleted)</label>
          <button
            class="book-button"
            type="submit"
            :disabled="bookingLoading"
          >
            {{ bookingLoading ? 'Creating…' : 'Create booking' }}
          </button>
          <p
            v-if="bookingMessage"
            class="notice success"
            role="status"
          >
            {{ bookingMessage }}
          </p>
          <p
            v-if="bookingError"
            class="notice error"
            role="alert"
          >
            {{ bookingError }}
          </p>
        </form>
        <div class="history-panel">
          <div class="history-heading">
            <h3>Booking history</h3><span>{{ bookings.length }} records</span>
          </div>
          <p
            v-if="bookings.length === 0"
            class="empty-history"
          >
            No bookings are available.
          </p>
          <article
            v-for="booking in bookings"
            :key="booking.booking_id"
            class="booking-card"
          >
            <div>
              <span
                class="status"
                :class="booking.status"
              >{{ booking.status }}</span><h4>{{ booking.trip_name }}</h4><p>{{ booking.display_name }} · {{ booking.hotel_name }}</p><small>{{ booking.booking_id }} · booked {{ booking.booked_on }}</small>
            </div>
            <div class="booking-actions">
              <button
                v-if="booking.status !== 'cancelled'"
                type="button"
                @click="cancelBooking(booking.booking_id)"
              >
                Cancel
              </button><button
                v-if="booking.is_test"
                class="delete"
                type="button"
                @click="deleteBooking(booking.booking_id)"
              >
                Delete test
              </button>
            </div>
          </article>
        </div>
      </div>
    </section>
  </main>
</template>
