/* Theme picker — replace Material's cycling toggle with a direct-select popover.
 *
 * Material stores palette preference in localStorage key "__palette":
 *   { "index": 0 | 1 | 2, "color": { ... } }
 * index corresponds to position in mkdocs.yml `theme.palette` list:
 *   0 → auto (prefers-color-scheme)
 *   1 → light (default scheme)
 *   2 → dark (slate scheme)
 *
 * We hide the default toggle and inject a <details>-based picker next to it.
 */
(function () {
  const SCHEMES = [
    { index: 0, icon: "🖥️", label: "Auto", hint: "Follow OS" },
    { index: 1, icon: "☀️", label: "Light", hint: "Always light" },
    { index: 2, icon: "🌙", label: "Dark", hint: "Always dark" },
  ];
  const STORAGE_KEY = "__palette";

  function getCurrentIndex() {
    try {
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
      const idx = parseInt(stored.index, 10);
      return Number.isInteger(idx) ? idx : 0;
    } catch (_e) {
      return 0;
    }
  }

  function applyScheme(index) {
    const current = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    current.index = index;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
    // Full reload is the cleanest way to re-apply Material's palette logic
    // including any contextual CSS variables.
    location.reload();
  }

  function inject() {
    const header = document.querySelector(".md-header__inner") || document.querySelector(".md-header");
    if (!header) return;
    if (header.querySelector(".lvt-theme-picker")) return; // idempotent

    const currentIdx = getCurrentIndex();

    const details = document.createElement("details");
    details.className = "lvt-theme-picker md-header__button";
    details.innerHTML = `
      <summary title="Choose color mode" aria-label="Choose color mode">
        ${SCHEMES[currentIdx]?.icon || "🎨"}
      </summary>
      <div class="lvt-theme-picker-menu" role="menu">
        ${SCHEMES
          .map(
            (s) => `
          <button type="button" role="menuitem" data-scheme="${s.index}" class="${s.index === currentIdx ? "is-active" : ""}">
            <span class="lvt-theme-picker-icon">${s.icon}</span>
            <span class="lvt-theme-picker-label">${s.label}</span>
            <span class="lvt-theme-picker-hint">${s.hint}</span>
          </button>`
          )
          .join("")}
      </div>
    `;

    // Insert right before the language switcher (if present) or at the end.
    const altSwitch = header.querySelector('[data-md-component="palette"]');
    if (altSwitch?.parentNode) {
      altSwitch.parentNode.insertBefore(details, altSwitch);
    } else {
      header.appendChild(details);
    }

    details.querySelectorAll("button[data-scheme]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.preventDefault();
        applyScheme(parseInt(btn.dataset.scheme, 10));
      });
    });

    // Close on click outside.
    document.addEventListener("click", (ev) => {
      if (!details.contains(ev.target) && details.open) details.open = false;
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", inject);
  } else {
    inject();
  }

  // Re-inject on SPA-style nav (Material instant) just in case.
  if (typeof document$ !== "undefined" && document$.subscribe) {
    document$.subscribe(inject);
  }
})();
