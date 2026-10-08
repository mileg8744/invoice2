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
  bindEntityPickers();
  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", () => {
      form.querySelectorAll(".js-krw").forEach((el) => {
        el.value = String(el.value || "").replace(/,/g, "");
      });
    });
  });

  bindAddressSearch();
  bindBulkInvoiceActions();
  bindEmailLists();
});

function bindEmailLists() {
  document.querySelectorAll("[data-email-list]").forEach((box) => {
    const name = box.getAttribute("data-email-list");
    const rows = box.querySelector(".email-rows");
    if (!rows) return;
    box.addEventListener("click", (ev) => {
      if (ev.target.closest(".js-email-add")) {
        ev.preventDefault();
        const row = document.createElement("div");
        row.className = "email-row d-flex gap-2 mb-2";
        row.innerHTML =
          `<input class="form-control" type="email" name="${name}" placeholder="">` +
          `<button class="btn btn-ghost js-email-del" type="button">${ev.target.textContent.includes("Add") ? "Delete" : "삭제"}</button>`;
        rows.appendChild(row);
        row.querySelector("input")?.focus();
      }
      if (ev.target.closest(".js-email-del")) {
        ev.preventDefault();
        ev.target.closest(".email-row")?.remove();
        if (!rows.querySelector(".email-row")) {
          const row = document.createElement("div");
          row.className = "email-row d-flex gap-2 mb-2";
          row.innerHTML =
            `<input class="form-control" type="email" name="${name}">` +
            `<button class="btn btn-ghost js-email-del" type="button">삭제</button>`;
          rows.appendChild(row);
        }
      }
    });
  });
}

function bindEntityPickers() {
  document.querySelectorAll("[data-entity-picker]").forEach((box) => {
    const companyEl = box.querySelector("[data-entity-company]");
    const regionEl = box.querySelector("[data-entity-region]");
    const countryEl = box.querySelector("[data-entity-country]");
    const target = box.querySelector("[data-entity-target]");
    if (!target) return;

    function matches(opt) {
      if (!opt.value) return true;
      const company = (companyEl && companyEl.value) || "";
      const region = (regionEl && regionEl.value) || "";
      const country = (countryEl && countryEl.value) || "";
      if (company && (opt.dataset.company || "") !== company) return false;
      if (region) {
        const ko = opt.dataset.region || "";
        const en = opt.dataset.regionEn || "";
        if (ko !== region && en !== region) return false;
      }
      if (country) {
        const ko = opt.dataset.country || "";
        const en = opt.dataset.countryEn || "";
        if (ko !== country && en !== country) return false;
      }
      return true;
    }

    function refresh() {
      const kept = target.value;
      let visible = 0;
      [...target.options].forEach((opt) => {
        const ok = matches(opt);
        opt.hidden = !ok;
        opt.disabled = !ok;
        if (ok && opt.value) visible += 1;
      });
      if (kept && target.selectedOptions[0] && target.selectedOptions[0].hidden) {
        target.value = "";
        target.dispatchEvent(new Event("change", { bubbles: true }));
      }
      target.dataset.entityVisible = String(visible);
    }

    [companyEl, regionEl, countryEl].forEach((el) => {
      el?.addEventListener("change", refresh);
    });
    refresh();
  });
}

function bindBulkInvoiceActions() {
  const form = document.getElementById("bulk-invoice-form");
  if (!form) return;
  const master = document.getElementById("select-invoices");
  const boxes = () => [...document.querySelectorAll(".js-invoice-check")];
  const needed = (kind) => {
    const selected = boxes().filter((el) => el.checked);
    if (kind === "remind") return selected.filter((el) => el.dataset.status === "issued");
    if (kind === "issue") return selected.filter((el) => el.dataset.status === "draft");
    return selected;
  };
  master?.addEventListener("change", () => {
    boxes().forEach((el) => {
      el.checked = master.checked;
    });
  });
  document.addEventListener("change", (ev) => {
    if (!master || !ev.target.classList.contains("js-invoice-check")) return;
    const all = boxes();
    master.checked = all.length > 0 && all.every((el) => el.checked);
  });
  function bulkKind(ev) {
    const fromSubmitter = ev && ev.submitter && ev.submitter.dataset.bulkAction;
    return fromSubmitter || form.dataset.pendingAction || "";
  }
  form.querySelectorAll("[data-bulk-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      form.dataset.pendingAction = btn.dataset.bulkAction || "";
    });
  });
  form.addEventListener("submit", (ev) => {
    const kind = bulkKind(ev);
    const selected = needed(kind);
    if (!selected.length) {
      ev.preventDefault();
      const key = kind === "issue" ? "needIssue" : kind === "delete" ? "needDelete" : "needRemind";
      window.alert(form.dataset[key] || "");
      return;
    }
    const confirmKey = kind === "issue" ? "confirmIssue" : kind === "delete" ? "confirmDelete" : "confirmRemind";
    if (!window.confirm(form.dataset[confirmKey] || "")) {
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

function pguMoneyFx(amountKrw, rate) {
  const krw = Number(amountKrw) || 0;
  const fxRate = Number(rate) || 0;
  if (!fxRate) return 0;
  return Math.round((krw / fxRate) * 100) / 100;
}

function pguFormatFx(amount, currency) {
  const n = Number(amount);
  const code = currency || "USD";
  if (!Number.isFinite(n)) return `${code} 0.00`;
  return `${code} ${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function pguRefreshFxCells({ rateEl, currencyEl, emptyText } = {}) {
  const rate = Number((rateEl && rateEl.value) || 0);
  const currency = (currencyEl && currencyEl.value) || "USD";
  const fallback = emptyText || "—";
  document.querySelectorAll(".js-fx-cell").forEach((el) => {
    const krw = Number(el.getAttribute("data-fx-krw") || 0);
    if (!rate) {
      el.textContent = fallback;
      el.classList.add("is-empty");
      return;
    }
    el.classList.remove("is-empty");
    el.textContent = pguFormatFx(pguMoneyFx(krw, rate), currency);
  });
}

window.pguParseKrw = pguParseKrw;
window.pguFormatKrw = pguFormatKrw;
window.pguBindKrw = bindKrwInputs;
window.pguMoneyFx = pguMoneyFx;
window.pguFormatFx = pguFormatFx;
window.pguRefreshFxCells = pguRefreshFxCells;

function uniqueSearchParts(parts) {
  const seen = new Set();
  const out = [];
  parts.forEach((part) => {
    const text = String(part || "").trim();
    if (!text) return;
    const key = text.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push(text);
  });
  return out;
}

function mapsSearchQuery(box) {
  const form = box.closest("form");
  const typed = (box.querySelector(".js-addr-q")?.value || "").trim();
  const company = (
    form?.querySelector('[name="name_en"]')?.value ||
    form?.querySelector('[name="pgu_name"]')?.value ||
    box.getAttribute("data-company") ||
    ""
  ).trim();
  const country = (
    form?.querySelector('[name="country_en"]')?.value ||
    box.getAttribute("data-country") ||
    ""
  ).trim();
  return uniqueSearchParts([typed, company, country]).join(" ");
}

function openGoogleMapsSearch(query) {
  const url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
  window.open(url, "_blank", "noopener,noreferrer");
}

function bindAddressSearch() {
  document.querySelectorAll(".addr-search").forEach((box) => {
    const input = box.querySelector(".js-addr-q");
    const googleBtn = box.querySelector(".js-addr-google");
    const target = box.querySelector(".js-addr-target");

    function runSearch() {
      const query = mapsSearchQuery(box);
      if (!query) {
        input?.focus();
        return;
      }
      openGoogleMapsSearch(query);
      target?.focus();
    }

    googleBtn?.addEventListener("click", runSearch);
    input?.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        runSearch();
      }
    });
  });
}

