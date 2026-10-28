(() => {
  const form = document.getElementById('trip-form');
  const searchButton = document.getElementById('search-button');
  const loading = document.getElementById('loading');
  const errorPanel = document.getElementById('error-panel');
  const welcome = document.getElementById('welcome');
  const resultsContent = document.getElementById('results-content');
  const locationHint = document.getElementById('location-hint');
  const fromInput = document.getElementById('origin');
  const toInput = document.getElementById('destination');
  let map = null;
  let mapLayers = null;

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[char]);
  }

  function showLoading(isLoading) {
    loading.classList.toggle('hidden', !isLoading);
    searchButton.disabled = isLoading;
    searchButton.querySelector('span:first-child').textContent = isLoading ? 'Searching online sources…' : 'Find my route & places';
    if (isLoading) {
      welcome.classList.add('hidden');
      errorPanel.classList.add('hidden');
      resultsContent.classList.add('hidden');
    }
  }

  function formatMoney(value) {
    return '₹' + Number(value || 0).toLocaleString('en-IN');
  }

  function setError(message) {
    errorPanel.textContent = message;
    errorPanel.classList.remove('hidden');
    resultsContent.classList.add('hidden');
    loading.classList.add('hidden');
    welcome.classList.add('hidden');
  }

  function summaryCard(label, value, sub) {
    return `<div class="summary-card"><div class="summary-label">${esc(label)}</div><div class="summary-value">${esc(value)}</div><div class="summary-sub">${esc(sub || '')}</div></div>`;
  }

  function renderTransport(items, selectedMode) {
    const container = document.getElementById('transport-table');
    if (!items || !items.length) {
      container.innerHTML = '<div class="empty-state">No transport estimates available.</div>';
      return;
    }
    container.innerHTML = items.map(item => {
      const selected = selectedMode === item.mode;
      return `<div class="transport-row ${selected ? 'selected' : ''}">
        <div class="transport-head"><strong>${esc(item.mode)}</strong><span>${formatMoney(item.low)}–${formatMoney(item.high)}</span></div>
        <div class="transport-meta">${Number(item.distance_km).toLocaleString('en-IN')} km · ${esc(item.time)} · ${esc(item.unit)}</div>
        <div class="transport-meta">${esc(item.note)}</div>
      </div>`;
    }).join('');
  }

  function renderPoiList(containerId, items, kind) {
    const container = document.getElementById(containerId);
    const icons = { hotels: '🏨', food: '🍲', attractions: '📍' };
    if (!items || !items.length) {
      container.innerHTML = `<div class="empty-state">No named ${kind} found in the nearby OpenStreetMap data. Try a nearby landmark or check the destination spelling.</div>`;
      return;
    }
    container.innerHTML = items.map(item => {
      const distance = `${Number(item.distance_km).toFixed(1)} km away`;
      const extra = [item.cuisine ? `Cuisine: ${item.cuisine}` : '', item.stars ? `OSM star tag: ${item.stars}` : '', item.opening_hours ? `Hours: ${item.opening_hours}` : ''].filter(Boolean).join(' · ');
      return `<article class="poi-card">
        <div class="poi-icon">${icons[kind] || '📍'}</div>
        <div class="poi-content"><h4>${esc(item.name)}</h4>
          <p>${esc(item.kind || kind)} · ${esc(distance)}</p>
          ${extra ? `<p>${esc(extra)}</p>` : ''}
          <div class="poi-actions"><a href="${esc(item.maps_url)}" target="_blank" rel="noopener">Open on Google Maps ↗</a>${item.website && /^https:\/\//i.test(item.website) ? `<a href="${esc(item.website)}" target="_blank" rel="noopener">Website ↗</a>` : ''}</div>
        </div>
      </article>`;
    }).join('');
  }

  function renderAttractions(items) {
    const container = document.getElementById('attraction-list');
    if (!items || !items.length) {
      container.innerHTML = '<div class="empty-state">No named attractions found nearby from OpenStreetMap.</div>';
      return;
    }
    container.innerHTML = items.map(item => `
      <article class="place-card">
        <div class="place-photo"><div class="photo-placeholder">📍</div></div>
        <div class="place-body"><h3>${esc(item.name)}</h3>
          <div class="place-sub">${esc(item.kind || 'Attraction')}</div>
          <div class="place-meta"><span>${Number(item.distance_km).toFixed(1)} km away</span></div>
          <a href="${esc(item.maps_url)}" target="_blank" rel="noopener">View place ↗</a>
        </div>
      </article>`).join('');
  }

  function renderMl(items, matchedCity) {
    const container = document.getElementById('ml-list');
    if (!items || !items.length) {
      const cityMessage = matchedCity
        ? `No sample attractions in ${matchedCity} match this budget and interest. Try increasing the budget or selecting All.`
        : 'Your destination is outside the six-city sample ML dataset. Live nearby places are still shown above; try Hyderabad, Vizag, Chennai, Bengaluru, Delhi, or Mumbai to see sample ML recommendations.';
      container.innerHTML = `<div class="empty-state">${esc(cityMessage)}</div>`;
      return;
    }
    container.innerHTML = items.map(item => {
      const photo = item.image_url && /^https:\/\//i.test(item.image_url)
        ? `<img loading="lazy" src="${esc(item.image_url)}" alt="Photo of ${esc(item.place)}" referrerpolicy="no-referrer" onerror="this.parentElement.innerHTML='<div class=\'photo-placeholder\'>🌄</div>'">`
        : '<div class="photo-placeholder">🌄</div>';
      return `<article class="place-card">
        <div class="place-photo">${photo}</div>
        <div class="place-body"><h3>${esc(item.place)}</h3>
          <div class="place-sub">${esc(item.city)} · ${esc(item.type)}</div>
          <div class="place-meta"><span>Sample cost ${formatMoney(item.cost)}</span><span>${Number(item.distance_km).toFixed(1)} km from city centre*</span></div>
          <div class="place-rating">Predicted rating: ${Number(item.predicted_rating).toFixed(2)} / 5</div>
          <div class="place-sub">Sample dataset rating: ${Number(item.sample_rating).toFixed(1)} / 5</div>
          <a href="${esc(item.maps_url)}" target="_blank" rel="noopener">View location ↗</a>
          ${item.image_search_url ? ` · <a href="${esc(item.image_search_url)}" target="_blank" rel="noopener">Find photos ↗</a>` : ''}
        </div>
      </article>`;
    }).join('');
  }

  function renderMap(data) {
    const mapElement = document.getElementById('map');
    if (!window.L) {
      document.getElementById('route-warning').textContent = 'Map library did not load. Use the external directions link instead.';
      document.getElementById('route-warning').classList.remove('hidden');
      return;
    }
    if (!map) {
      map = L.map(mapElement, { scrollWheelZoom: false });
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>'
      }).addTo(map);
      mapLayers = L.featureGroup().addTo(map);
    }
    mapLayers.clearLayers();
    const origin = data.origin;
    const destination = data.destination;
    const boundsPoints = [];

    const originMarker = L.marker([origin.lat, origin.lon]).bindPopup(`<b>From:</b> ${esc(origin.display_name || origin.name)}`);
    const destinationMarker = L.marker([destination.lat, destination.lon]).bindPopup(`<b>To:</b> ${esc(destination.display_name || destination.name)}`);
    originMarker.addTo(mapLayers);
    destinationMarker.addTo(mapLayers);
    boundsPoints.push([origin.lat, origin.lon], [destination.lat, destination.lon]);

    if (data.route && data.route.geometry) {
      const line = L.geoJSON(data.route.geometry, {
        style: { color: '#186b54', weight: 5, opacity: 0.85 }
      });
      line.addTo(mapLayers);
      try { boundsPoints.push(...line.getBounds().toLatLngs().flat().map(p => [p.lat, p.lng])); } catch (_) {}
    }

    const poiGroups = [
      ...(data.nearby?.hotels || []).slice(0, 5),
      ...(data.nearby?.food || []).slice(0, 5),
      ...(data.nearby?.attractions || []).slice(0, 5)
    ];
    poiGroups.forEach(item => {
      const marker = L.circleMarker([item.lat, item.lon], {
        radius: 6, color: '#fff', weight: 2,
        fillColor: '#e49a40', fillOpacity: 0.95
      }).bindPopup(`<b>${esc(item.name)}</b><br>${esc(item.kind || '')}<br>${Number(item.distance_km).toFixed(1)} km from destination`);
      marker.addTo(mapLayers);
      boundsPoints.push([item.lat, item.lon]);
    });

    if (boundsPoints.length) map.fitBounds(boundsPoints, { padding: [25, 25], maxZoom: 13 });
    setTimeout(() => map.invalidateSize(), 120);

    const routeWarning = document.getElementById('route-warning');
    routeWarning.classList.toggle('hidden', !!(data.route && data.route.source && data.route.source.startsWith('OSRM')));
    if (!routeWarning.classList.contains('hidden')) {
      routeWarning.textContent = data.route?.source || 'The map line may be approximate, not a road route.';
    }
  }

  function renderPlan(data) {
    welcome.classList.add('hidden');
    errorPanel.classList.add('hidden');
    resultsContent.classList.remove('hidden');

    const originName = data.origin.display_name || data.origin.name;
    const destinationName = data.destination.display_name || data.destination.name;
    document.getElementById('route-title').textContent = `${data.origin.name} to ${data.destination.name}`;
    document.getElementById('route-subtitle').textContent = `${originName} → ${destinationName}`;
    document.getElementById('directions-link').href = data.directions_url;

    const routeDistance = Number(data.route.distance_km || 0);
    const routeDuration = data.route.duration_minutes != null
      ? `${Math.round(data.route.duration_minutes)} min`
      : 'Not available';
    const routeSub = data.route.source || 'Route estimate';
    document.getElementById('route-summary').innerHTML = [
      summaryCard('ROAD DISTANCE', `${routeDistance.toFixed(1)} km`, routeSub),
      summaryCard('DRIVING TIME', routeDuration, 'Not live traffic; real time may vary'),
      summaryCard('STRAIGHT-LINE DISTANCE', `${Number(data.straight_line_distance_km).toFixed(1)} km`, 'Geographic distance, not road distance')
    ].join('');

    const selectedMode = document.getElementById('mode').value;
    renderTransport(data.transport_budgets, selectedMode === 'Compare all' ? '' : selectedMode);
    renderPoiList('hotel-list', data.nearby?.hotels || [], 'hotels');
    renderPoiList('food-list', data.nearby?.food || [], 'food');
    renderAttractions(data.nearby?.attractions || []);
    renderMl(data.ml_recommendations || [], data.ml_city_match);
    renderMap(data);

    const notes = data.source_notes || [];
    const nearbyWarning = data.nearby?.warning;
    document.getElementById('source-notes').innerHTML = `
      <strong>Data sources and limitations</strong><br>
      ${notes.map(note => `<div>• ${esc(note)}</div>`).join('')}
      ${nearbyWarning ? `<div class="inline-note">${esc(nearbyWarning)}</div>` : ''}
      <div>• Nearby places: OpenStreetMap contributors, under the Open Database License. Always check a venue's current opening hours and contact details before travelling.</div>
    `;
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const origin = fromInput.value.trim();
    const destination = toInput.value.trim();
    if (!origin || !destination) {
      setError('Please enter both a starting location and a destination.');
      return;
    }

    showLoading(true);
    try {
      const response = await fetch('/api/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          origin,
          destination,
          mode: document.getElementById('mode').value,
          budget: document.getElementById('budget').value,
          interest: document.getElementById('interest').value
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Unable to plan this trip.');
      renderPlan(data);
      document.getElementById('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
      setError(error.message || 'A network error occurred. Check your internet connection and try again.');
    } finally {
      showLoading(false);
    }
  });

  document.getElementById('swap-locations').addEventListener('click', () => {
    const oldOrigin = fromInput.value;
    fromInput.value = toInput.value;
    toInput.value = oldOrigin;
  });

  document.getElementById('use-location').addEventListener('click', () => {
    locationHint.textContent = 'Requesting browser location permission…';
    if (!navigator.geolocation) {
      locationHint.textContent = 'Geolocation is not available in this browser. Type a starting location instead.';
      return;
    }
    navigator.geolocation.getCurrentPosition(position => {
      const lat = position.coords.latitude.toFixed(6);
      const lon = position.coords.longitude.toFixed(6);
      fromInput.value = `@${lat},${lon}`;
      locationHint.textContent = 'Current coordinates added. Location was accessed only after you allowed it.';
    }, () => {
      locationHint.textContent = 'Location permission was not granted. Enter your starting city or address manually.';
    }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
  });
})();
