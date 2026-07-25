(function () {
  function update(frame) {
    const output = frame.querySelector(".shiny-bound-output, .shiny-html-output, .shiny-plot-output, .shiny-data-frame-output");
    if (!output) return;
    const hasContent = output.children.length > 0 || output.textContent.trim().length > 0;
    const busy = output.classList.contains("recalculating");
    frame.classList.toggle("is-loaded", hasContent && !busy);
  }

  function scan(root) {
    (root || document).querySelectorAll(".loading-frame").forEach((frame) => {
      update(frame);
      if (frame.dataset.skeletonObserved) return;
      frame.dataset.skeletonObserved = "true";
      new MutationObserver(() => update(frame)).observe(frame, {
        childList: true,
        subtree: true,
        characterData: true,
        attributes: true,
        attributeFilter: ["class"],
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    scan(document);
    new MutationObserver((mutations) => mutations.forEach((mutation) =>
      mutation.addedNodes.forEach((node) => node.nodeType === 1 && scan(node))
    )).observe(document.body, { childList: true, subtree: true });
  });
})();
