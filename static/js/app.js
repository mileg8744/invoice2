document.addEventListener("DOMContentLoaded", () => {
  const alerts = document.querySelectorAll(".alert");
  alerts.forEach((el) => {
    setTimeout(() => {
      el.classList.add("fade");
    }, 6000);
  });

  const KEY = "pgu.sidebarCollapsed";
  const hideBtn = document.getElementById("btnHideSidebar");
  const showBtn = document.getElementById("btnShowSidebar");
  const restoreBtn = document.getElementById("btnRestoreSidebar");

  function setCollapsed(collapsed) {
    document.documentElement.classList.toggle("sidebar-collapsed", collapsed);
    try {
      localStorage.setItem(KEY, collapsed ? "1" : "0");
    } catch (e) {}
  }

  hideBtn?.addEventListener("click", () => setCollapsed(true));
  showBtn?.addEventListener("click", () => setCollapsed(false));
  restoreBtn?.addEventListener("click", () => setCollapsed(false));

  bindKrwInputs(document);
  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", () => {
      form.querySelectorAll(".js-krw").forEach((el) => {
        el.value = String(el.value || "").replace(/,/g, "");
      });
    });
  });

  loadGoogleMaps(window.PGU_GOOGLE_MAPS_KEY || "", bindAddressSearch);
  bindBulkRemind();
});

function bindBulkRemind() {
  const form = document.getElementById("bulk-remind-form");
  if (!form) return;
  const master = document.getElementById("select-issued");
  const boxes = () => [...document.querySelectorAll(".js-issued-check:not(:disabled)")];
  master?.addEventListener("change", () => {
    boxes().forEach((el) => {
      el.checked = master.checked;
    });
  });
  document.addEventListener("change", (ev) => {
    if (!master || !ev.target.classList.contains("js-issued-check")) return;
    const all = boxes();
    master.checked = all.length > 0 && all.every((el) => el.checked);
  });
  form.addEventListener("submit", (ev) => {
    const selected = boxes().filter((el) => el.checked).length;
    if (!selected) {
      ev.preventDefault();
      window.alert(form.dataset.needOne || "");
      return;
    }
    if (!window.confirm(form.dataset.confirm || "")) {
      ev.preventDefault();
    }
  });
}

function pguParseKrw(value) {
  return Number(String(value || "").replace(/[^\d-]/g, "")) || 0;
}

function pguFormatKrw(value) {
  const n = pguParseKrw(value);
  return n ? n.toLocaleString("en-US") : "";
}

function bindKrwInputs(root) {
  (root || document).querySelectorAll(".js-krw").forEach((el) => {
    if (el.dataset.krwBound) return;
    el.dataset.krwBound = "1";
    el.addEventListener("input", () => {
      const start = el.selectionStart;
      const before = el.value || "";
      el.value = pguFormatKrw(before);
      if (typeof start === "number") {
        const diff = el.value.length - before.length;
        try {
          el.setSelectionRange(start + diff, start + diff);
        } catch (e) {}
      }
    });
    if (el.value) el.value = pguFormatKrw(el.value);
  });
}

window.pguParseKrw = pguParseKrw;
window.pguFormatKrw = pguFormatKrw;
window.pguBindKrw = bindKrwInputs;

function loadGoogleMaps(key, done) {
  if (window.google && window.google.maps && window.google.maps.places) {
    done();
    return;
  }
  if (!key) {
    done();
    return;
  }
  const existing = document.getElementById("google-maps-sdk");
  if (existing) {
    existing.addEventListener("load", () => done(), { once: true });
    existing.addEventListener("error", () => done(), { once: true });
    return;
  }
  const script = document.createElement("script");
  script.id = "google-maps-sdk";
  script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&libraries=places&language=en`;
  script.async = true;
  script.onload = () => done();
  script.onerror = () => done();
  document.head.appendChild(script);
}

function bindAddressSearch() {
  const boxes = document.querySelectorAll(".addr-search");
  if (!boxes.length) return;
  const googleReady = Boolean(window.google && window.google.maps && window.google.maps.places);

  boxes.forEach((box) => {
    const input = box.querySelector(".js-addr-q");
    const results = box.querySelector(".js-addr-results");
    const target = box.querySelector(".js-addr-target");
    const googleBtn = box.querySelector(".js-addr-google");
    const noneText = box.getAttribute("data-empty") || "검색 결과가 없습니다.";
    const countryInput = box.closest("form")?.querySelector('[name="country_en"]');
    let timer = null;
    let seq = 0;

    function hideResults() {
      if (!results) return;
      results.hidden = true;
      results.innerHTML = "";
    }

    function showItems(items) {
      if (!results) return;
      results.innerHTML = "";
      if (!items.length) {
        const li = document.createElement("li");
        li.className = "addr-empty";
        li.textContent = noneText;
        results.appendChild(li);
        results.hidden = false;
        return;
      }
      items.forEach((item) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.innerHTML = `<span>${escapeHtml(item.label).replace(/\n/g, "<br>")}</span>`;
        if (item.detail && item.detail !== item.label) {
          const small = document.createElement("small");
          small.textContent = item.detail;
          btn.appendChild(small);
        }
        btn.addEventListener("click", () => {
          target.value = item.label;
          input.value = "";
          hideResults();
          target.focus();
        });
        li.appendChild(btn);
        results.appendChild(li);
      });
      results.hidden = false;
    }

    async function runSearch(query) {
      const current = ++seq;
      try {
        const country = (countryInput?.value || box.getAttribute("data-country") || "").trim();
        const url = `/api/address-search?q=${encodeURIComponent(query)}&country=${encodeURIComponent(country)}`;
        const res = await fetch(url, { headers: { Accept: "application/json" } });
        const data = await res.json();
        if (current !== seq) return;
        showItems((data && data.items) || []);
      } catch (e) {
        if (current !== seq) return;
        showItems([]);
      }
    }

    function searchPlaces(query, done) {
      if (googleReady && window.google.maps.places.AutocompleteService) {
        const svc = new window.google.maps.places.AutocompleteService();
        svc.getPlacePredictions({ input: query, types: ["geocode"] }, (preds) => {
          if (!preds || !preds.length) {
            done(null);
            return;
          }
          done(
            preds.map((p) => ({
              label: p.description,
              detail: (p.structured_formatting && p.structured_formatting.secondary_text) || "",
            }))
          );
        });
        return;
      }
      done(null);
    }

    if (googleReady && input) {
      const ac = new window.google.maps.places.Autocomplete(input, {
        fields: ["formatted_address", "address_components", "name"],
        types: ["geocode"],
      });
      ac.addListener("place_changed", () => {
        const place = ac.getPlace();
        if (place && place.formatted_address) {
          target.value = place.formatted_address;
          input.value = "";
          hideResults();
          target.focus();
        }
      });
    }

    input?.addEventListener("input", () => {
      const query = (input.value || "").trim();
      clearTimeout(timer);
      if (query.length < 3) {
        hideResults();
        return;
      }
      timer = setTimeout(() => {
        searchPlaces(query, (items) => {
          if (items) showItems(items);
          else runSearch(query);
        });
      }, 350);
    });

    input?.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        clearTimeout(timer);
        googleBtn?.click();
      }
      if (ev.key === "Escape") hideResults();
    });

    document.addEventListener("click", (ev) => {
      if (!box.contains(ev.target)) hideResults();
    });

    googleBtn?.addEventListener("click", () => {
      const query = (input?.value || "").trim();
      if (query.length < 3) {
        input?.focus();
        return;
      }
      searchPlaces(query, (items) => {
        if (items) showItems(items);
        else runSearch(query);
      });
    });
  });
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

