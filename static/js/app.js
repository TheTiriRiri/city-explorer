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

    // Retry context
    const retryFn = ref(null);

    /* ---- Computed ---- */
    const totalCityPages = computed(() =>
      Math.max(1, Math.ceil(cityTotal.value / cityPerPage.value))
    );

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
      } catch (e) {
        errorMsg.value = e.message || "Failed to load city information.";
        retryFn.value = fetchCityInfo;
      } finally {
        loading.value = false;
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
      formatPopulation,
      escapeHtml,
    };
  },
});

app.mount("#app");
