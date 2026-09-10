<script setup>
import { computed, ref } from 'vue'

const hotelName = ref('')
const results = ref([])
const hasSearched = ref(false)
const isLoading = ref(false)
const errorMessage = ref('')

const tableRows = computed(() =>
  results.value.flatMap((hotel) => {
    if (hotel.available_stays.length === 0) {
      return [{ hotel, stay: null }]
    }

    return hotel.available_stays.map((stay) => ({ hotel, stay }))
  }),
)

async function searchHotels() {
  hasSearched.value = true
  isLoading.value = true
  errorMessage.value = ''
  results.value = []

  try {
    const response = await fetch(
      `/api/hotels/search?name=${encodeURIComponent(hotelName.value)}`,
    )

    if (!response.ok) {
      throw new Error(`Search request failed with status ${response.status}`)
    }

    const data = await response.json()
    results.value = data.results
  } catch {
    errorMessage.value =
      'Unable to reach the hotel search service. Ensure the FastAPI backend is running.'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <main>
    <h1>Expedia Lite</h1>

    <form @submit.prevent="searchHotels">
      <label for="hotel-name">Hotel name</label>
      <input
        id="hotel-name"
        v-model="hotelName"
        type="search"
      >
      <button
        type="submit"
        :disabled="isLoading"
      >
        {{ isLoading ? 'Searching…' : 'Search' }}
      </button>
    </form>

    <p
      v-if="errorMessage"
      role="alert"
    >
      {{ errorMessage }}
    </p>

    <p
      v-else-if="hasSearched && !isLoading && results.length === 0"
      role="status"
    >
      No hotels matched your search.
    </p>

    <table v-else-if="results.length > 0">
      <caption>
        Matching hotels and available stays
      </caption>
      <thead>
        <tr>
          <th scope="col">
            Hotel ID
          </th>
          <th scope="col">
            Hotel Name
          </th>
          <th scope="col">
            City
          </th>
          <th scope="col">
            State
          </th>
          <th scope="col">
            Nightly Rate (USD)
          </th>
          <th scope="col">
            Trip ID
          </th>
          <th scope="col">
            Trip Name
          </th>
          <th scope="col">
            Check In
          </th>
          <th scope="col">
            Check Out
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in tableRows"
          :key="`${row.hotel.hotel_id}-${row.stay?.trip_id ?? 'none'}`"
        >
          <td>{{ row.hotel.hotel_id }}</td>
          <td>{{ row.hotel.hotel_name }}</td>
          <td>{{ row.hotel.city }}</td>
          <td>{{ row.hotel.state }}</td>
          <td>{{ row.hotel.nightly_rate_usd }}</td>
          <td>{{ row.stay?.trip_id ?? '—' }}</td>
          <td>{{ row.stay?.trip_name ?? '—' }}</td>
          <td>{{ row.stay?.check_in ?? '—' }}</td>
          <td>{{ row.stay?.check_out ?? '—' }}</td>
        </tr>
      </tbody>
    </table>
  </main>
</template>
