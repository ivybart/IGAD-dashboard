(function () {
  function setShinyTextInput(input, value) {
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function locationErrorMessage(error) {
    if (error.code === error.PERMISSION_DENIED) {
      return "Location permission was blocked. Allow location access in your browser settings, then try again.";
    }
    if (error.code === error.TIMEOUT) {
      return "Location lookup timed out. Move near a window, enable Wi-Fi or device location services, then try again.";
    }
    return "No location fix is available. Enable Wi-Fi or device location services, then try again.";
  }

  document.addEventListener("click", function (event) {
    const button = event.target.closest("button[id$='capture_location']");
    if (!button) return;

    const panel = button.closest(".geo-capture");
    const status = panel.querySelector(".location-status");
    const prefix = button.id.slice(0, -"capture_location".length);
    const latitude = document.getElementById(prefix + "latitude");
    const longitude = document.getElementById(prefix + "longitude");

    if (!navigator.geolocation) {
      status.textContent = "Location capture is not supported on this device. You can enter coordinates manually.";
      status.classList.add("location-error");
      return;
    }

    if (!window.isSecureContext) {
      status.textContent = "Location capture requires HTTPS or localhost. Open the app using a secure address, or enter coordinates manually.";
      status.classList.add("location-error");
      return;
    }

    button.disabled = true;
    status.textContent = "Finding your location…";
    status.classList.remove("location-error", "location-success");

    function success(position) {
        setShinyTextInput(latitude, position.coords.latitude.toFixed(6));
        setShinyTextInput(longitude, position.coords.longitude.toFixed(6));
        status.textContent = `Location captured · accuracy approximately ${Math.round(position.coords.accuracy)} metres. Review before sending.`;
        status.classList.add("location-success");
        button.disabled = false;
        button.textContent = "Refresh my location";
    }

    function finalFailure(error) {
        status.textContent = `${locationErrorMessage(error)} Manual coordinates are still available.`;
        status.classList.add("location-error");
        button.disabled = false;
        button.textContent = "Try location again";
    }

    function retryWithNetwork(error) {
      if (error.code === error.PERMISSION_DENIED) {
        finalFailure(error);
        return;
      }
      status.textContent = "GPS fix unavailable · trying network-based location…";
      navigator.geolocation.getCurrentPosition(
        success,
        finalFailure,
        { enableHighAccuracy: false, timeout: 25000, maximumAge: 300000 }
      );
    }

    navigator.geolocation.getCurrentPosition(
      success,
      retryWithNetwork,
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 }
    );
  });
})();
