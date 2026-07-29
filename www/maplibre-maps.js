(function () {
  const maps = new WeakMap();

  function initMap(el) {
    if (!el || maps.has(el) || typeof maplibregl === "undefined") return;

    const points = JSON.parse(el.dataset.points || "[]");
    const center = JSON.parse(el.dataset.center || "[40,1]");
    const zoom = Number(el.dataset.zoom || 4.3);
    const rasterTiles = el.dataset.rasterTiles;
    const rasterBounds = el.dataset.rasterBounds ? JSON.parse(el.dataset.rasterBounds) : null;
    const rasterMinzoom = Number(el.dataset.rasterMinzoom || 4);
    const rasterMaxzoom = Number(el.dataset.rasterMaxzoom || 14);
    const polygonData = el.dataset.geojson ? JSON.parse(el.dataset.geojson) : null;
    const showControls = el.dataset.showControls !== "false";
    const locked = el.dataset.locked === "true";
    const fitGeojson = el.dataset.fitGeojson === "true";
    const map = new maplibregl.Map({
      container: el,
      style: "https://tiles.openfreemap.org/styles/dark",
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
        const rasterLayerId = "grassland-raster";
        const wardOpacity = (grasslandVisible) => [
          "case",
          ["boolean", ["feature-state", "hover"], false], 0.92,
          ["has", "in_focus"], [
            "case",
            ["boolean", ["get", "in_focus"], false], grasslandVisible ? 0.52 : 0.82,
            grasslandVisible ? 0.08 : 0.14
          ],
          grasslandVisible ? 0.38 : 0.7
        ];
        const loadRasterLayer = (controlMap) => {
          if (controlMap.getSource("grassland-raster")) return;
          controlMap.addSource("grassland-raster", {
            type: "raster",
            tiles: [rasterTiles],
            tileSize: 256,
            minzoom: rasterMinzoom,
            maxzoom: rasterMaxzoom,
            ...(rasterBounds ? { bounds: rasterBounds } : {}),
          });
          controlMap.addLayer({
            id: rasterLayerId,
            type: "raster",
            source: "grassland-raster",
            paint: { "raster-opacity": 1, "raster-fade-duration": 250 },
          }, controlMap.getLayer("indicator-fill") ? "indicator-fill" : undefined);
        };

        class RasterToggleControl {
          onAdd(controlMap) {
            this.map = controlMap;
            this.container = document.createElement("div");
            this.container.className = "maplibregl-ctrl maplibregl-ctrl-group grassland-layer-control";
            const label = document.createElement("label");
            label.title = "Show or hide ESA grassland cover";
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.checked = false;
            checkbox.setAttribute("aria-label", "Show ESA grassland cover");
            const text = document.createElement("span");
            text.textContent = "ESA grassland cover";
            checkbox.addEventListener("change", () => {
              if (checkbox.checked) loadRasterLayer(controlMap);
              if (controlMap.getLayer(rasterLayerId)) {
                controlMap.setLayoutProperty(rasterLayerId, "visibility", checkbox.checked ? "visible" : "none");
              }
              if (controlMap.getLayer("indicator-fill")) {
                controlMap.setPaintProperty("indicator-fill", "fill-opacity", wardOpacity(checkbox.checked));
              }
            });
            label.append(checkbox, text);
            this.container.append(label);
            return this.container;
          }
          onRemove() {
            this.container?.remove();
            this.map = undefined;
          }
        }
        map.addControl(new RasterToggleControl(), "top-right");
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
            "fill-opacity": [
              "case",
              ["boolean", ["feature-state", "hover"], false], 0.9,
              ["has", "in_focus"], ["case", ["boolean", ["get", "in_focus"], false], rasterTiles ? 0.82 : 0.78, rasterTiles ? 0.14 : 0.34],
              rasterTiles ? 0.42 : 0.7
            ],
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
            "line-color": [
              "case",
              ["boolean", ["get", "selected"], false], "#f3b746",
              ["has", "in_focus"], ["case", ["boolean", ["get", "in_focus"], false], "#ffd166", "rgba(221,235,229,.34)"],
              "rgba(255,255,255,.84)"
            ],
            "line-width": [
              "case",
              ["boolean", ["get", "selected"], false], 3.5,
              ["has", "in_focus"], ["case", ["boolean", ["get", "in_focus"], false], 2.25, 0.55],
              1.25
            ],
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
          const title = properties.ADM3_EN
            ? `${properties.ADM3_EN} ward`
            : (properties.ADM1_EN || "Monitoring area");
          const details = [properties.detail_1, properties.detail_2, properties.detail_3]
            .filter(Boolean)
            .map((detail) => `<span>${detail}</span>`)
            .join("");
          new maplibregl.Popup({ closeButton: false, maxWidth: "300px" })
            .setLngLat(event.lngLat)
            .setHTML(`<div class="map-popup"><strong>${title}</strong><span>${properties.ADM1_EN || ""} · ${properties.landscape || "Twende landscape"}</span><hr><span>${properties.indicator || "Indicator"} <b>${properties.display_value || "No data"}</b></span>${details}</div>`)
            .addTo(map);
        });
      });
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
