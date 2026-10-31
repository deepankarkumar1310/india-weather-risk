/* India Weather Risk – map client. No build step; plain JS + Leaflet. */
(() => {
  "use strict";

  const LEVELS = ["Low", "Moderate", "High", "Severe"];
  const THRESHOLDS = [0, 0.15, 0.35, 0.6];
  const HAZARD_LABEL = { overall: "Overall", flood: "Flood", heat: "Heat" };
  const $ = (id) => document.getElementById(id);

  const state = { hazard: "overall", day: null, snap: null, geo: null, layer: null, selected: null, byCode: {} };

  // ---------- theme ----------
  const store = {
    get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
  };
  const prefersLight = window.matchMedia && matchMedia("(prefers-color-scheme: light)").matches;
  const setTheme = (t) => { document.documentElement.dataset.theme = t; store.set("theme", t); };
  setTheme(store.get("theme") || (prefersLight ? "light" : "dark"));
  $("theme").onclick = () => {
    setTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light");
    restyle();
  };
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  // ---------- helpers ----------
  const levelOf = (s) => LEVELS[THRESHOLDS.filter((t) => s >= t).length - 1];
  const colour = (s) => (s == null ? css("--nodata") : css("--" + levelOf(s).toLowerCase()));
  const pct = (s) => Math.round(s * 100);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtDate = (iso, opts) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", opts);

  function scoreFor(r) {
    if (!r) return null;
    if (state.day == null) return r[state.hazard];
    const d = r.daily.find((x) => x.date === state.day);
    return d ? d[state.hazard] : null;
  }

  // ---------- map ----------
  const map = L.map("map", { zoomControl: true, attributionControl: true, minZoom: 4, maxZoom: 10, zoomSnap: 0.25, preferCanvas: true });
  map.attributionControl.setPrefix(false);
  map.attributionControl.addAttribution('Weather data by <a href="https://open-meteo.com/">Open-Meteo.com</a>');
  map.zoomControl.setPosition("bottomright");

  function fitIndia() {
    const wide = window.innerWidth > 760;
    map.fitBounds([[6.5, 68], [37.2, 97.5]], {
      paddingTopLeft: wide ? [370, 20] : [10, 50],
      paddingBottomRight: wide ? [20, 20] : [10, window.innerHeight * 0.46],
    });
  }

  function styleFeature(f) {
    const s = scoreFor(state.byCode[f.properties.code]);
    const sel = state.selected === f.properties.code;
    return {
      fillColor: colour(s),
      fillOpacity: 1,
      color: sel ? css("--text") : css("--land-stroke"),
      weight: sel ? 2.5 : 0.6,
    };
  }

  function restyle() {
    if (!state.layer) return;
    state.layer.setStyle(styleFeature);
    renderLegend();
  }

  function drawMap() {
    state.layer = L.geoJSON(state.geo, {
      style: styleFeature,
      onEachFeature: (f, layer) => {
        const code = f.properties.code;
        layer.bindTooltip(() => {
          const r = state.byCode[code];
          if (!r) return `<b>${esc(f.properties.state)}</b><br><span class="muted">No data</span>`;
          const s = scoreFor(r);
          return `<b>${esc(r.name)}</b>, ${esc(r.state)}<br>${HAZARD_LABEL[state.hazard]} risk: <span class="badge ${levelOf(s)}">${levelOf(s)} · ${pct(s)}</span>`;
        }, { className: "tip", sticky: true, direction: "top", offset: [0, -8] });
        layer.on("click", () => state.byCode[code] && select(code, false));
      },
    }).addTo(map);
    fitIndia();
  }

  // ---------- sidebar ----------
  function renderDays() {
    const box = $("days");
    const btn = (label, sub, value) => {
      const b = document.createElement("button");
      b.innerHTML = `${label}<small>${sub}</small>`;
      b.setAttribute("aria-pressed", String(state.day === value));
      b.onclick = () => { state.day = value; renderAll(); };
      return b;
    };
    box.replaceChildren(
      btn("7-day", "peak", null),
      ...state.snap.dates.map((d) => btn(fmtDate(d, { weekday: "short" }), fmtDate(d, { day: "numeric", month: "short" }), d)),
    );
  }

  function renderStats() {
    const rows = Object.values(state.snap.districts);
    const counts = Object.fromEntries(LEVELS.map((l) => [l, 0]));
    let exposed = 0;
    for (const r of rows) {
      const s = scoreFor(r);
      if (s == null) continue;
      const l = levelOf(s);
      counts[l]++;
      if (l === "High" || l === "Severe") exposed += r.population || 0;
    }
    const crore = exposed / 1e7;
    $("stats").innerHTML =
      [...LEVELS].reverse().map((l) =>
        `<div class="stat"><b>${counts[l]}</b><span><i class="dot" style="background:var(--${l.toLowerCase()})"></i>${l}</span></div>`).join("") +
      `<div class="stat wide"><span>People in High/Severe districts</span><b>${crore >= 1 ? crore.toFixed(1) + " crore" : (exposed / 1e5).toFixed(1) + " lakh"}</b></div>`;
  }

  function renderTop() {
    const rows = Object.values(state.snap.districts)
      .map((r) => ({ r, s: scoreFor(r) }))
      .filter((x) => x.s != null)
      .sort((a, b) => b.s - a.s)
      .slice(0, 10);
    const when = state.day ? fmtDate(state.day, { weekday: "short", day: "numeric", month: "short" }) : "next 7 days";
    $("top-title").textContent = `Highest ${HAZARD_LABEL[state.hazard].toLowerCase()} risk · ${when}`;
    $("top-list").replaceChildren(...rows.map(({ r, s }) => {
      const li = document.createElement("li");
      li.innerHTML = `<button><span>${esc(r.name)}</span><small>${esc(r.state)}</small><span class="score badge ${levelOf(s)}">${pct(s)}</span></button>`;
      li.firstChild.onclick = () => select(r.code, true);
      return li;
    }));
  }

  function renderLegend() {
    $("legend").innerHTML = LEVELS.map((l, i) =>
      `<span><i class="dot" style="background:var(--${l.toLowerCase()})"></i>${l}${i ? ` ≥${pct(THRESHOLDS[i])}` : ""}</span>`).join("") +
      `<span><i class="dot" style="background:var(--nodata)"></i>No data</span>`;
  }

  function renderAll() {
    document.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.hazard === state.hazard)));
    renderDays();
    renderStats();
    renderTop();
    restyle();
    if (state.selected != null) renderDetail(state.byCode[state.selected]);
  }

  // ---------- detail ----------
  function meter(label, s) {
    return `<div class="meter"><span>${label}</span><div class="track"><div class="fill" style="width:${pct(s)}%;background:${colour(s)}"></div></div><b>${pct(s)}</b></div>`;
  }

  function chart(daily) {
    const W = 340, H = 150, pad = { l: 28, r: 28, t: 12, b: 30 };
    const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b, n = daily.length, bw = iw / n;
    const maxRain = Math.max(20, ...daily.map((d) => d.rain_mm));
    const temps = daily.map((d) => d.tmax);
    const tLo = Math.floor(Math.min(...temps) - 2), tHi = Math.ceil(Math.max(...temps) + 2);
    const x = (i) => pad.l + bw * i + bw / 2;
    const yR = (v) => pad.t + ih - (v / maxRain) * ih;
    const yT = (v) => pad.t + ih - ((v - tLo) / (tHi - tLo)) * ih;
    const bars = daily.map((d, i) => `<rect class="rain" x="${x(i) - bw * 0.3}" y="${yR(d.rain_mm)}" width="${bw * 0.6}" height="${pad.t + ih - yR(d.rain_mm)}" rx="2"><title>${d.rain_mm} mm</title></rect>`).join("");
    const line = daily.map((d, i) => `${i ? "L" : "M"}${x(i)},${yT(d.tmax)}`).join("");
    const dots = daily.map((d, i) => `<circle class="tdot" cx="${x(i)}" cy="${yT(d.tmax)}" r="3"><title>${d.tmax} °C</title></circle>`).join("");
    const labels = daily.map((d, i) => `<text x="${x(i)}" y="${H - 14}" text-anchor="middle">${fmtDate(d.date, { weekday: "short" })}</text><text x="${x(i)}" y="${H - 3}" text-anchor="middle">${fmtDate(d.date, { day: "numeric" })}</text>`).join("");
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="7-day rain and temperature chart">
      <line class="grid" x1="${pad.l}" x2="${W - pad.r}" y1="${pad.t + ih}" y2="${pad.t + ih}"/>
      <text x="${pad.l - 4}" y="${pad.t + 4}" text-anchor="end">${Math.round(maxRain)}</text>
      <text x="${pad.l - 4}" y="${pad.t + ih}" text-anchor="end">0</text>
      <text x="${W - pad.r + 4}" y="${pad.t + 4}">${tHi}°</text>
      <text x="${W - pad.r + 4}" y="${pad.t + ih}">${tLo}°</text>
      ${bars}<path class="tmax" d="${line}"/>${dots}${labels}</svg>
      <div class="key"><span><i style="background:#4aa3df"></i>Rain (mm)</span><span><i style="background:var(--high)"></i>Max temp (°C)</span></div>`;
  }

  function renderDetail(r) {
    const s = r.overall;
    const pop = r.population ? `${(r.population / 1e5).toFixed(1)} lakh people (2011)` : "";
    $("detail-body").innerHTML = `
      <h2>${esc(r.name)}</h2>
      <p class="sub muted">${esc(r.state)}${pop ? " · " + pop : ""}</p>
      <span class="badge ${r.level}">${r.level} risk · peak ${fmtDate(r.peak_date, { weekday: "short", day: "numeric", month: "short" })}</span>
      <div class="meters">${meter("Overall", r.overall)}${meter("Flood", r.flood)}${meter("Heat", r.heat)}</div>
      <h3>Why</h3>
      <ul class="drivers">${r.drivers.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>
      <h3>7-day forecast</h3>
      <div class="chart">${chart(r.daily)}</div>
      <table class="table">
        <thead><tr><th>Day</th><th>Rain</th><th>Max</th><th>Feels</th><th>Risk</th></tr></thead>
        <tbody>${r.daily.map((d) => `<tr><td>${fmtDate(d.date, { weekday: "short", day: "numeric" })}</td><td>${d.rain_mm} mm</td><td>${d.tmax}°</td><td>${d.feels_like ?? "–"}°</td><td><span class="badge ${d.level}">${pct(d.overall)}</span></td></tr>`).join("")}</tbody>
      </table>
      <p class="muted" style="font-size:12px;margin-top:12px">Vulnerability index ${r.vulnerability.toFixed(2)}${r.vulnerability_imputed ? " (estimated from state median)" : ""}
        → hazard × ${r.vulnerability_weight.toFixed(2)}. Score ${pct(s)}/100.</p>`;
    $("detail").hidden = false;
  }

  function select(code, fly) {
    const prev = state.selected;
    state.selected = code;
    const r = state.byCode[code];
    renderDetail(r);
    restyle();
    history.replaceState(null, "", "#d=" + code);
    if (fly) {
      state.layer.eachLayer((l) => { if (l.feature.properties.code === code) map.flyToBounds(l.getBounds(), { maxZoom: 7, duration: 0.6 }); });
    }
    if (prev !== code) state.layer.eachLayer((l) => { if (l.feature.properties.code === code) l.bringToFront(); });
  }

  $("close").onclick = () => {
    $("detail").hidden = true;
    state.selected = null;
    history.replaceState(null, "", location.pathname + location.search);
    restyle();
  };

  document.querySelectorAll(".seg button").forEach((b) => { b.onclick = () => { state.hazard = b.dataset.hazard; renderAll(); }; });

  $("search").addEventListener("change", (e) => {
    const q = e.target.value.trim().toLowerCase();
    const hit = Object.values(state.snap.districts).find((r) => `${r.name}, ${r.state}`.toLowerCase() === q)
      || Object.values(state.snap.districts).find((r) => r.name.toLowerCase().startsWith(q.split(",")[0]));
    if (hit) { select(hit.code, true); e.target.blur(); }
  });

  // ---------- boot ----------
  // The single-file build (scripts/build_standalone.py) embeds the data so it opens without a server.
  const embedded = window.EMBEDDED_DATA;
  Promise.all(embedded ? [embedded.geo, embedded.snap] : [
    fetch("data/districts.geojson").then((r) => { if (!r.ok) throw new Error("map"); return r.json(); }),
    fetch("data/latest.json", { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error("forecast"); return r.json(); }),
  ]).then(([geo, snap]) => {
    state.geo = geo;
    state.snap = snap;
    state.byCode = Object.fromEntries(Object.values(snap.districts).map((r) => [r.code, r]));
    const gen = new Date(snap.generated_at);
    $("updated").textContent = `Forecast updated ${gen.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} · ${snap.district_count} districts`;
    $("district-list").innerHTML = Object.values(snap.districts)
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((r) => `<option value="${esc(r.name)}, ${esc(r.state)}">`).join("");
    drawMap();
    renderAll();
    const m = location.hash.match(/d=(\d+)/);
    if (m && state.byCode[+m[1]]) select(+m[1], true);
  }).catch((err) => {
    $("updated").innerHTML = `<div class="error">Couldn't load ${err.message === "forecast" ? "the forecast" : "the map"}. Try refreshing.</div>`;
  });

  window.addEventListener("resize", () => state.layer && !state.selected && fitIndia());
})();
