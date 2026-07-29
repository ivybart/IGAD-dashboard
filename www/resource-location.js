(function () {
  function activeStatus() {
    return document.querySelector(".modal.show .resource-location-status");
  }

  function setStatus(message, state) {
    const status = activeStatus();
    if (!status) return;
    status.textContent = message;
    status.classList.remove("location-error", "location-success");
    if (state) status.classList.add(state);
  }

  function updateInput(input, value) {
    if (!input) throw new Error("Coordinate input is not available");
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  document.addEventListener("click", function (event) {
    const button = event.target.closest("button[id$='use_resource_location']");
    if (!button) return;

    const prefix = button.id.slice(0, -"use_resource_location".length);
    const latitude = document.getElementById(prefix + "resource_latitude");
    const longitude = document.getElementById(prefix + "resource_longitude");

    if (!window.isSecureContext) {
      setStatus("Location access requires HTTPS, localhost, or 127.0.0.1. Use town search or manual coordinates on this connection.", "location-error");
      return;
    }

    if (!navigator.geolocation) {
      setStatus("Location capture is unavailable in this browser. Search for a Kenyan town or enter coordinates manually.", "location-error");
      return;
    }

    button.disabled = true;
    setStatus("Waiting for your browser's location permission...", null);
    navigator.geolocation.getCurrentPosition(
      function (position) {
        try {
          updateInput(latitude, position.coords.latitude.toFixed(6));
          updateInput(longitude, position.coords.longitude.toFixed(6));
          setStatus(`Location captured - approximately ${Math.round(position.coords.accuracy)} m accuracy. Review before saving.`, "location-success");
        } catch {
          setStatus("Your location was found, but the coordinate fields could not be updated. Reopen the form and try again.", "location-error");
        }
        button.disabled = false;
      },
      function (error) {
        const messages = {
          1: "Location permission was denied. Allow location access in your browser settings, then try again.",
          2: "Your device could not determine a location. Search for a Kenyan town or enter coordinates manually.",
          3: "Location lookup timed out. Move near a window or enable device location, then try again."
        };
        setStatus(messages[error.code] || "Your location could not be determined. Search for a Kenyan town or enter coordinates manually.", "location-error");
        button.disabled = false;
      },
      { enableHighAccuracy: true, timeout: 30000, maximumAge: 300000 }
    );
  });

  document.addEventListener("change", function (event) {
    if (!event.target.matches("input[id$='resource_latitude'], input[id$='resource_longitude']")) return;
    const modal = event.target.closest(".modal");
    const latitude = modal?.querySelector("input[id$='resource_latitude']")?.value;
    const longitude = modal?.querySelector("input[id$='resource_longitude']")?.value;
    if (latitude && longitude) {
      setStatus("Coordinates are ready. Review them before saving.", "location-success");
    }
  });
})();
