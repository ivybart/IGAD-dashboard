(function () {
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";

  function scrollPageToTop() {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }

  function isPrimaryNavigationTab(target) {
    return target instanceof Element && Boolean(target.closest(".navbar-nav [data-bs-toggle='tab']"));
  }

  // Reset before Bootstrap swaps panels so the previous page position is never painted.
  document.addEventListener("pointerdown", function (event) {
    if (isPrimaryNavigationTab(event.target)) scrollPageToTop();
  }, true);

  document.addEventListener("keydown", function (event) {
    if ((event.key === "Enter" || event.key === " ") && isPrimaryNavigationTab(event.target)) {
      scrollPageToTop();
    }
  }, true);

  document.addEventListener("show.bs.tab", function (event) {
    if (isPrimaryNavigationTab(event.target)) scrollPageToTop();
  }, true);
})();
