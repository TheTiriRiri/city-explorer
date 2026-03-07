/* ============================================================
   City Explorer - Vue 3 SPA (CDN / Options API)
   ============================================================ */

const { createApp, ref, computed, watch, onMounted, nextTick } = Vue;

/* --- Helpers --- */

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}

function debounce(fn, ms) {
  let timer = null;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), ms);
  };
}

function formatPopulation(n) {
  if (n == null) return "N/A";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

/* --- App --- */

const app = createApp({
  setup() {
    /* ---- State ---- */
    const view = ref("countries"); // "countries" | "cities" | "city"
    const loading = ref(false);
    const errorMsg = ref("");

    // Countries
    const countries = ref([]);
    const countrySearch = ref("");

    // Cities
    const selectedCountry = ref(null); // { name, code, flag_url }
    const cities = ref([]);
    const citySearch = ref("");
    const cityPage = ref(1);
    const cityPerPage = ref(20);
    const cityTotal = ref(0);
    const countryName = ref("");

    // City profile
    const selectedCity = ref(null); // { name }
    const cityInfo = ref(null);

    // Enrichment: photos, timeline, POIs
    const photos = ref([]);
    const photosLoading = ref(false);
    const photosError = ref("");
    const photoFilter = ref("all");

    const timeline = ref([]);
    const timelineLoading = ref(false);
    const timelineError = ref("");

    const pois = ref([]);
    const poisLoading = ref(false);
    const poisError = ref("");
    const poiFilter = ref("all");

    // Retry context
    const retryFn = ref(null);

    /* ---- Computed ---- */
    const totalCityPages = computed(() =>
      Math.max(1, Math.ceil(cityTotal.value / cityPerPage.value))
    );

    const photoCategories = computed(() => {
      const cats = new Set(photos.value.map(p => p.category));
      return ["all", ...Array.from(cats).sort()];
    });

    const filteredPhotos = computed(() => {
      if (photoFilter.value === "all") return photos.value;
      return photos.value.filter(p => p.category === photoFilter.value);
    });

    const poiCategories = computed(() => {
      const cats = new Set(pois.value.map(p => p.category));
      return ["all", ...Array.from(cats).sort()];
    });

    const filteredPois = computed(() => {
      if (poiFilter.value === "all") return pois.value;
      return pois.value.filter(p => p.category === poiFilter.value);
    });

    /* ---- API helpers ---- */
    async function apiFetch(url) {
      const resp = await fetch(url);
      if (!resp.ok) {
        let errText = "An unexpected error occurred.";
        try {
          const body = await resp.json();
          if (body.error && body.error.message) {
            errText = body.error.message;
          } else if (body.detail) {
            if (typeof body.detail === "string") {
              errText = body.detail;
            } else if (body.detail.error && body.detail.error.message) {
              errText = body.detail.error.message;
            }
          }
        } catch {
          /* ignore parse errors */
        }
        throw new Error(errText);
      }
      return resp.json();
    }

    /* ---- Fetch countries ---- */
    async function fetchCountries() {
      loading.value = true;
      errorMsg.value = "";
      retryFn.value = null;
      try {
        let url = "/countries";
        if (countrySearch.value.trim()) {
          url += "?search=" + encodeURIComponent(countrySearch.value.trim());
        }
        const data = await apiFetch(url);
        countries.value = data.countries;
      } catch (e) {
        errorMsg.value = e.message || "Failed to load countries.";
        retryFn.value = fetchCountries;
      } finally {
        loading.value = false;
      }
    }

    /* ---- Fetch cities ---- */
    async function fetchCities() {
      loading.value = true;
      errorMsg.value = "";
      retryFn.value = null;
      try {
        const code = selectedCountry.value.code;
        let url = `/countries/${encodeURIComponent(code)}/cities?page=${cityPage.value}&per_page=${cityPerPage.value}`;
        if (citySearch.value.trim()) {
          url += "&search=" + encodeURIComponent(citySearch.value.trim());
        }
        const data = await apiFetch(url);
        cities.value = data.cities;
        cityTotal.value = data.total;
        countryName.value = data.country_name;
      } catch (e) {
        errorMsg.value = e.message || "Failed to load cities.";
        retryFn.value = fetchCities;
      } finally {
        loading.value = false;
      }
    }

    /* ---- Fetch city info ---- */
    async function fetchCityInfo() {
      loading.value = true;
      errorMsg.value = "";
      retryFn.value = null;
      try {
        const name = selectedCity.value.name;
        const code = selectedCountry.value.code;
        const url = `/city/${encodeURIComponent(name)}/info?country_code=${encodeURIComponent(code)}`;
        const data = await apiFetch(url);
        cityInfo.value = data;
        // Trigger lazy loading of enrichment data
        fetchEnrichmentData(name, data.coordinates);
      } catch (e) {
        errorMsg.value = e.message || "Failed to load city information.";
        retryFn.value = fetchCityInfo;
      } finally {
        loading.value = false;
      }
    }

    /* ---- Enrichment: lazy-loaded sections ---- */
    function fetchEnrichmentData(cityName, coordinates) {
      // Reset state
      photos.value = [];
      photosError.value = "";
      photoFilter.value = "all";
      timeline.value = [];
      timelineError.value = "";
      pois.value = [];
      poisError.value = "";
      poiFilter.value = "all";

      // Fetch all three in parallel
      fetchPhotos(cityName);
      fetchTimeline(cityName);
      if (coordinates && coordinates.latitude && coordinates.longitude) {
        fetchPois(cityName, coordinates.latitude, coordinates.longitude);
      }
    }

    async function fetchPhotos(cityName) {
      photosLoading.value = true;
      try {
        const data = await apiFetch(`/city/${encodeURIComponent(cityName)}/photos?limit=12`);
        photos.value = data.photos || [];
      } catch (e) {
        photosError.value = "Failed to load photos.";
      } finally {
        photosLoading.value = false;
      }
    }

    async function fetchTimeline(cityName) {
      timelineLoading.value = true;
      try {
        const data = await apiFetch(`/city/${encodeURIComponent(cityName)}/timeline`);
        timeline.value = data.events || [];
      } catch (e) {
        timelineError.value = "Failed to load timeline.";
      } finally {
        timelineLoading.value = false;
      }
    }

    async function fetchPois(cityName, lat, lon) {
      poisLoading.value = true;
      try {
        const data = await apiFetch(`/city/${encodeURIComponent(cityName)}/pois?lat=${lat}&lon=${lon}`);
        pois.value = data.pois || [];
      } catch (e) {
        poisError.value = "Failed to load points of interest.";
      } finally {
        poisLoading.value = false;
      }
    }

    /* ---- Navigation ---- */
    function goToCountries() {
      view.value = "countries";
      selectedCountry.value = null;
      selectedCity.value = null;
      cityInfo.value = null;
      cities.value = [];
      citySearch.value = "";
      cityPage.value = 1;
      errorMsg.value = "";
      fetchCountries();
    }

    function goToCities(country) {
      selectedCountry.value = {
        name: country.name,
        code: country.code,
        flag_url: country.flag_url,
      };
      view.value = "cities";
      selectedCity.value = null;
      cityInfo.value = null;
      citySearch.value = "";
      cityPage.value = 1;
      errorMsg.value = "";
      fetchCities();
    }

    function goToCityProfile(city) {
      selectedCity.value = { name: city.name };
      view.value = "city";
      errorMsg.value = "";
      fetchCityInfo();
    }

    function goBackToCities() {
      view.value = "cities";
      selectedCity.value = null;
      cityInfo.value = null;
      errorMsg.value = "";
      fetchCities();
    }

    /* ---- Pagination ---- */
    function prevPage() {
      if (cityPage.value > 1) {
        cityPage.value--;
        fetchCities();
      }
    }

    function nextPage() {
      if (cityPage.value < totalCityPages.value) {
        cityPage.value++;
        fetchCities();
      }
    }

    /* ---- Debounced searches ---- */
    const debouncedCountrySearch = debounce(() => {
      fetchCountries();
    }, 300);

    const debouncedCitySearch = debounce(() => {
      cityPage.value = 1;
      fetchCities();
    }, 300);

    function onCountrySearchInput(e) {
      countrySearch.value = e.target.value;
      debouncedCountrySearch();
    }

    function onCitySearchInput(e) {
      citySearch.value = e.target.value;
      debouncedCitySearch();
    }

    /* ---- Retry ---- */
    function handleRetry() {
      if (retryFn.value) {
        retryFn.value();
      }
    }

    /* ---- Display helpers (used in template) ---- */
    function personYears(person) {
      if (!person.birth_year && !person.death_year) return "";
      const b = person.birth_year || "?";
      const d = person.death_year ? person.death_year : "";
      if (d) return `(${b}\u2013${d})`;
      return `(b. ${b})`;
    }

    function personInitial(person) {
      return person.name ? person.name.charAt(0).toUpperCase() : "?";
    }

    function flagUrl(code) {
      if (!code) return "";
      return `https://flagcdn.com/${code.toLowerCase()}.svg`;
    }

    function poiIcon(category) {
      const icons = {
        museum: "\u{1F3DB}",
        attraction: "\u{2B50}",
        monument: "\u{1F3F0}",
        park: "\u{1F333}",
        religious: "\u{26EA}",
        restaurant: "\u{1F37D}",
      };
      return icons[category] || "\u{1F4CD}";
    }

    /* ---- Init ---- */
    onMounted(() => {
      fetchCountries();
    });

    return {
      view,
      loading,
      errorMsg,
      countries,
      countrySearch,
      selectedCountry,
      cities,
      citySearch,
      cityPage,
      cityPerPage,
      cityTotal,
      countryName,
      selectedCity,
      cityInfo,
      totalCityPages,
      retryFn,
      // Enrichment
      photos,
      photosLoading,
      photosError,
      photoFilter,
      photoCategories,
      filteredPhotos,
      timeline,
      timelineLoading,
      timelineError,
      pois,
      poisLoading,
      poisError,
      poiFilter,
      poiCategories,
      filteredPois,
      // Methods
      fetchCountries,
      fetchCities,
      fetchCityInfo,
      goToCountries,
      goToCities,
      goToCityProfile,
      goBackToCities,
      prevPage,
      nextPage,
      onCountrySearchInput,
      onCitySearchInput,
      handleRetry,
      personYears,
      personInitial,
      flagUrl,
      poiIcon,
      formatPopulation,
      escapeHtml,
    };
  },
});

app.mount("#app");
