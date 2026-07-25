(function () {
  const maps = new WeakMap();

  function initMap(el) {
    if (!el || maps.has(el) || typeof maplibregl === "undefined") return;

    const points = JSON.parse(el.dataset.points || "[]");
    const center = JSON.parse(el.dataset.center || "[40,1]");
    const zoom = Number(el.dataset.zoom || 4.3);
    const shouldGeolocate = el.dataset.geolocate === "true";
    const rasterTiles = el.dataset.rasterTiles;
    const rasterBounds = el.dataset.rasterBounds ? JSON.parse(el.dataset.rasterBounds) : null;
    const polygonData = el.dataset.geojson ? JSON.parse(el.dataset.geojson) : null;
    const showControls = el.dataset.showControls !== "false";
    const locked = el.dataset.locked === "true";
    const fitGeojson = el.dataset.fitGeojson === "true";
    const map = new maplibregl.Map({
      container: el,
      style: shouldGeolocate
        ? "https://tiles.openfreemap.org/styles/bright"
        : "https://tiles.openfreemap.org/styles/dark",
      center,
      zoom,
      minZoom: 3,
      maxZoom: 14,
      attributionControl: false,
      dragPan: !locked,
      scrollZoom: !locked,
      boxZoom: !locked,
      doubleClickZoom: !locked,
      keyboard: !locked,
      touchZoomRotate: !locked,
    });

    if (showControls) {
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
    }

    if (rasterTiles) {
      map.on("load", () => {
        map.addSource("median-ndvi", {
          type: "raster",
          tiles: [rasterTiles],
          tileSize: 256,
          minzoom: 4,
          maxzoom: 14,
          ...(rasterBounds ? { bounds: rasterBounds } : {}),
        });
        map.addLayer({ id: "median-ndvi", type: "raster", source: "median-ndvi", paint: { "raster-opacity": 0.78, "raster-fade-duration": 250 } });
      });
    }

    if (polygonData) {
      map.on("load", () => {
        map.addSource("indicator-polygons", { type: "geojson", data: polygonData, generateId: true });
        map.addLayer({
          id: "indicator-fill",
          type: "fill",
          source: "indicator-polygons",
          paint: {
            "fill-color": ["coalesce", ["get", "fill_color"], "#81918b"],
            "fill-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 0.88, 0.7],
          },
        });

        if (fitGeojson) {
          const bounds = new maplibregl.LngLatBounds();
          const extendCoordinates = (coordinates) => {
            if (!Array.isArray(coordinates)) return;
            if (typeof coordinates[0] === "number" && typeof coordinates[1] === "number") {
              bounds.extend(coordinates);
              return;
            }
            coordinates.forEach(extendCoordinates);
          };
          polygonData.features?.forEach((feature) => extendCoordinates(feature.geometry?.coordinates));
          if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 46, duration: 0 });
        }
        map.addLayer({
          id: "indicator-outline",
          type: "line",
          source: "indicator-polygons",
          paint: {
            "line-color": ["case", ["boolean", ["get", "selected"], false], "#f3b746", "rgba(255,255,255,.84)"],
            "line-width": ["case", ["boolean", ["get", "selected"], false], 3.5, 1.25],
          },
        });

        let hoveredId = null;
        map.on("mousemove", "indicator-fill", (event) => {
          map.getCanvas().style.cursor = "pointer";
          if (hoveredId !== null) map.setFeatureState({ source: "indicator-polygons", id: hoveredId }, { hover: false });
          hoveredId = event.features?.[0]?.id ?? null;
          if (hoveredId !== null) map.setFeatureState({ source: "indicator-polygons", id: hoveredId }, { hover: true });
        });
        map.on("mouseleave", "indicator-fill", () => {
          map.getCanvas().style.cursor = "";
          if (hoveredId !== null) map.setFeatureState({ source: "indicator-polygons", id: hoveredId }, { hover: false });
          hoveredId = null;
        });
        map.on("click", "indicator-fill", (event) => {
          const properties = event.features?.[0]?.properties || {};
          new maplibregl.Popup({ closeButton: false, maxWidth: "285px" })
            .setLngLat(event.lngLat)
            .setHTML(`<div class="map-popup"><strong>${properties.ADM1_EN || "Monitoring area"}</strong><span>${properties.landscape || "Twende landscape"}</span><hr><span>${properties.indicator || "Indicator"} <b>${properties.display_value || "No data"}</b></span><span>Click another county to compare</span></div>`)
            .addTo(map);
        });
      });
    }

    if (shouldGeolocate) {
      const geolocate = new maplibregl.GeolocateControl({
        positionOptions: { enableHighAccuracy: true },
        trackUserLocation: true,
        showUserLocation: true,
        showAccuracyCircle: true,
      });
      map.addControl(geolocate, "top-right");

      geolocate.on("geolocate", (event) => {
        const pane = el.closest(".tab-pane") || document;
        const latitude = pane.querySelector("input[id$='latitude']");
        const longitude = pane.querySelector("input[id$='longitude']");
        const status = pane.querySelector(".location-status");
        if (latitude && longitude) {
          latitude.value = Number(event.coords.latitude).toFixed(6);
          longitude.value = Number(event.coords.longitude).toFixed(6);
          latitude.dispatchEvent(new Event("input", { bubbles: true }));
          longitude.dispatchEvent(new Event("input", { bubbles: true }));
          latitude.dispatchEvent(new Event("change", { bubbles: true }));
          longitude.dispatchEvent(new Event("change", { bubbles: true }));
        }
        if (status) {
          status.textContent = `MapLibre location active · accuracy approximately ${Math.round(event.coords.accuracy)} metres. Coordinates added to the report.`;
          status.classList.remove("location-error");
          status.classList.add("location-success");
        }
      });

      geolocate.on("error", (error) => {
        const pane = el.closest(".tab-pane") || document;
        const status = pane.querySelector(".location-status");
        if (status) {
          status.textContent = error.code === 1
            ? "Location permission was blocked. Allow it in browser settings, then use the map location button."
            : "MapLibre could not obtain a location fix. Enable device location services and Wi-Fi, then retry.";
          status.classList.add("location-error");
        }
      });

      map.once("load", () => geolocate.trigger());
    }

    points.forEach((point) => {
      const marker = document.createElement("button");
      marker.type = "button";
      marker.className = "resilience-marker";
      marker.style.setProperty("--marker-color", point.color || "#1d7c72");
      marker.style.setProperty("--marker-size", `${point.size || 18}px`);
      marker.setAttribute("aria-label", point.name || point.type || "Map location");

      const popup = new maplibregl.Popup({ offset: 18, closeButton: false, maxWidth: "270px" })
        .setHTML(`<div class="map-popup">${point.popup || point.name || "Location"}</div>`);

      new maplibregl.Marker({ element: marker, anchor: "center" })
        .setLngLat([Number(point.lon), Number(point.lat)])
        .setPopup(popup)
        .addTo(map);
    });

    maps.set(el, map);
    map.once("load", () => map.resize());
  }

  function scan(root) {
    (root || document).querySelectorAll(".maplibre-map").forEach(initMap);
  }

  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => mutation.addedNodes.forEach((node) => {
      if (node.nodeType !== 1) return;
      if (node.matches?.(".maplibre-map")) initMap(node);
      scan(node);
    }));
  });

  document.addEventListener("DOMContentLoaded", () => {
    scan();
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener("shown.bs.tab", () => {
      document.querySelectorAll(".maplibre-map").forEach((el) => maps.get(el)?.resize());
    });
  });
})();
