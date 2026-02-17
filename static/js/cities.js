const resultsContainer = document.getElementById("cityResults");
const form = document.getElementById("citySearchForm");
const input = document.getElementById("citySearchInput");
const countLabel = document.getElementById("citySearchCount");

async function fetchCities(query = "") {
  const url = query ? `/api/cities?q=${encodeURIComponent(query)}` : "/api/cities";
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch cities: ${response.statusText}`);
  }
  return response.json();
}

// Direct image overrides for known cities to guarantee real photos
// Keys support both 'city-state' and 'city' in lowercase with spaces as dashes
const CITY_IMAGE_OVERRIDES = {
  // Kochi, Kerala
  "kochi-kerala": [
    "https://upload.wikimedia.org/wikipedia/commons/5/5b/Chinese_nets%2C_Kochi%2C_India.jpg",
  ],
  "kochi": [
    "https://upload.wikimedia.org/wikipedia/commons/5/5b/Chinese_nets%2C_Kochi%2C_India.jpg",
  ],
  // Nagpur, Maharashtra
  "nagpur-maharashtra": [
    "https://upload.wikimedia.org/wikipedia/commons/9/9b/Deekshabhoomi_Stupa_Nagpur.jpg",
  ],
  "nagpur": [
    "https://upload.wikimedia.org/wikipedia/commons/9/9b/Deekshabhoomi_Stupa_Nagpur.jpg",
  ],
  // Salem, Tamil Nadu
  "salem-tamil-nadu": [
    "https://upload.wikimedia.org/wikipedia/commons/4/4f/Salem_junction_panorama.jpg",
  ],
  "salem": [
    "https://upload.wikimedia.org/wikipedia/commons/4/4f/Salem_junction_panorama.jpg",
  ],
};


function createCityCard(item) {
  const wrapper = document.createElement("article");
  wrapper.className = "city-card";

  // Optional city image from API (image_url) with extension fallback and SVG data URI fallback
  const sanitize = (s) => String(s || '')
    .toLowerCase()
    .replace(/[(),]/g, ' ')
    .replace(/\s+&\s+/g, ' and ')
    .replace(/\s+/g, '-');
  const slug = sanitize(`${item.city}-${item.state}`);
  const cityOnly = sanitize(item.city);
  const img = document.createElement('img');
  img.alt = `${item.city}, ${item.state}`;
  img.loading = 'lazy';
  img.style.width = '100%';
  img.style.borderRadius = '0.75rem';
  img.style.border = '1px solid rgba(55, 65, 81, 0.35)';
  img.style.display = 'block';

  const candidates = [
    // Strong overrides first, then API-provided URL, then local fallbacks
    ...((CITY_IMAGE_OVERRIDES[slug] || [])),
    ...((CITY_IMAGE_OVERRIDES[cityOnly] || [])),
    ...(item.image_url ? [item.image_url] : []),
    `/static/images/cities/${slug}.jpg`,
    `/static/images/cities/${slug}.png`,
    `/static/images/cities/${slug}.svg`,
  ];

  function svgFallback() {
    const bg = '#0ea5e9';
    const fg = '#0f172a';
    const label = `${item.city}, ${item.state}`.replace(/&/g, '&amp;').replace(/</g, '&lt;');
    const svg = `<?xml version="1.0" encoding="UTF-8"?><svg xmlns="http://www.w3.org/2000/svg" width="800" height="420" viewBox="0 0 800 420"><defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#0ea5e955"/><stop offset="1" stop-color="#38bdf855"/></linearGradient></defs><rect width="800" height="420" fill="#020617"/><rect x="16" y="16" width="768" height="388" rx="12" fill="url(#g)" stroke="#334155"/><text x="50%" y="52%" dominant-baseline="middle" text-anchor="middle" fill="#e5e7eb" font-family="Segoe UI, Arial, sans-serif" font-size="32" letter-spacing="1.5">${label}</text></svg>`;
    img.src = 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg);
    img.onerror = null;
  }

  let idx = 0;
  function tryNext() {
    if (idx < candidates.length) {
      img.src = candidates[idx++];
    } else {
      svgFallback();
    }
  }
  img.onerror = tryNext;
  tryNext();
  wrapper.appendChild(img);

  // Omit photo credit/links per requirement

  const header = document.createElement("header");
  header.className = "city-card__header";
  header.innerHTML = `
    <div>
      <h3>${item.city}, ${item.state}</h3>
      <p class="city-card__classification">${item.classification.replace("_", " ")}</p>
    </div>
    <div class="city-card__score">
      <span class="score">${item.suitability.score}</span>
      <span class="label">${item.suitability.priority} priority</span>
    </div>
  `;
  wrapper.appendChild(header);

  // Landmark (if available)
  if (item.landmark_name && item.landmark_name.trim()) {
    const lm = document.createElement('div');
    lm.className = 'city-card__section';
    const name = item.landmark_name.trim();
    if (item.landmark_url && item.landmark_url.trim()) {
      lm.innerHTML = `<strong>Landmark:</strong> <a href="${item.landmark_url}" target="_blank" rel="noopener">${name}</a>`;
    } else {
      lm.innerHTML = `<strong>Landmark:</strong> ${name}`;
    }
    wrapper.appendChild(lm);
  }

  const metricGrid = document.createElement("div");
  metricGrid.className = "city-card__metrics";
  metricGrid.innerHTML = `
    <div>
      <span class="metric-label">Avg delay</span>
      <span class="metric-value">${item.avg_delay_minutes} min</span>
    </div>
    <div>
      <span class="metric-label">Peak speed</span>
      <span class="metric-value">${item.avg_peak_speed_kmph} km/h</span>
    </div>
    <div>
      <span class="metric-label">Population</span>
      <span class="metric-value">${item.population_millions.toFixed(1)} M</span>
    </div>
  `;
  wrapper.appendChild(metricGrid);

  const issues = document.createElement("div");
  issues.className = "city-card__section";
  issues.innerHTML = `
    <h4>Current challenges</h4>
    <ul>${item.issues.map((issue) => `<li>${issue}</li>`).join("")}</ul>
  `;
  wrapper.appendChild(issues);

  const actions = document.createElement("div");
  actions.className = "city-card__section actions";
  actions.innerHTML = `
    <h4>How the platform helps</h4>
    <ul>${item.recommended_actions.map((action) => `<li>${action}</li>`).join("")}</ul>
  `;
  wrapper.appendChild(actions);

  const rationale = document.createElement("div");
  rationale.className = "city-card__section rationale";
  rationale.innerHTML = `
    <h4>Suitability rationale</h4>
    <p>${item.suitability.rationale.join(" • ")}</p>
  `;
  wrapper.appendChild(rationale);

  return wrapper;
}

function renderCityResults(data) {
  resultsContainer.innerHTML = "";
  if (!data.items || data.items.length === 0) {
    const emptyState = document.createElement("div");
    emptyState.className = "city-empty";
    emptyState.innerHTML = `
      <h3>No cities found</h3>
      <p>Try searching by state name, metro type, or another spelling.</p>
    `;
    resultsContainer.appendChild(emptyState);
    countLabel.textContent = "No matches";
    return;
  }

  const fragment = document.createDocumentFragment();
  data.items.forEach((item) => {
    fragment.appendChild(createCityCard(item));
  });
  resultsContainer.appendChild(fragment);

  countLabel.textContent = data.count ? `${data.count} city recommendations` : "Showing featured cities";
}

async function handleSearch(event) {
  event.preventDefault();
  const query = input.value.trim();
  try {
    countLabel.textContent = "Loading...";
    const data = await fetchCities(query);
    renderCityResults(data);
  } catch (error) {
    console.error(error);
    resultsContainer.innerHTML = `
      <div class="city-error">
        <h3>Could not load cities</h3>
        <p>${error.message}</p>
      </div>
    `;
    countLabel.textContent = "Error loading data";
  }
}

form?.addEventListener("submit", handleSearch);

// auto-load featured cities
fetchCities()
  .then(renderCityResults)
  .catch((error) => {
    console.error(error);
    resultsContainer.innerHTML = `
      <div class="city-error">
        <h3>Could not load cities</h3>
        <p>${error.message}</p>
      </div>
    `;
  });
