// Mock Canvas interactions: global-nav trays, nav collapse, course-nav toggle,
// module collapse, and the Account tray's accessibility toggles.

(function () {
  const store = {
    get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch {} },
  };
  const backdrop = document.getElementById("tray-backdrop");

  // ---- trays (Account, Courses, History, Help)
  function closeTrays() {
    document.querySelectorAll(".tray.open").forEach((t) => t.classList.remove("open"));
    document.querySelectorAll(".gnav-item.open").forEach((a) => a.classList.remove("open"));
    backdrop.classList.remove("open");
  }
  document.querySelectorAll("[data-tray]").forEach((link) => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      const tray = document.getElementById(`tray-${link.dataset.tray}`);
      const wasOpen = tray.classList.contains("open");
      closeTrays();
      if (!wasOpen) {
        tray.classList.add("open");
        link.classList.add("open");
        backdrop.classList.add("open");
        tray.querySelector(".tray-close").focus();
      }
    });
  });
  document.querySelectorAll(".tray-close").forEach((b) => b.addEventListener("click", closeTrays));
  backdrop.addEventListener("click", closeTrays);
  document.addEventListener("keydown", (e) => e.key === "Escape" && closeTrays());

  // ---- persisted body-class toggles
  function bindPref(cls, apply) {
    if (store.get(cls) === "1") document.body.classList.add(cls);
    apply?.(document.body.classList.contains(cls));
    return () => {
      const on = document.body.classList.toggle(cls);
      store.set(cls, on ? "1" : "0");
      apply?.(on);
    };
  }

  document.getElementById("gnav-collapse").addEventListener("click", bindPref("gnav-min"));
  const courseToggle = document.getElementById("course-nav-toggle");
  if (courseToggle) courseToggle.addEventListener("click", bindPref("course-nav-hidden"));

  document.querySelectorAll("[data-pref]").forEach((box) => {
    const toggle = bindPref(box.dataset.pref, (on) => (box.checked = on));
    box.addEventListener("change", toggle);
  });

  // ---- modules
  document.querySelectorAll(".module .mod-header:not(.static)").forEach((h) => {
    h.addEventListener("click", () => {
      const collapsed = h.closest(".module").classList.toggle("collapsed");
      h.setAttribute("aria-expanded", String(!collapsed));
      syncCollapseAll();
    });
  });
  const collapseAll = document.getElementById("collapse-all");
  function syncCollapseAll() {
    if (!collapseAll) return;
    const mods = [...document.querySelectorAll(".module")];
    collapseAll.textContent = mods.every((m) => m.classList.contains("collapsed")) ? "Expand All" : "Collapse All";
  }
  collapseAll?.addEventListener("click", () => {
    const collapse = collapseAll.textContent === "Collapse All";
    document.querySelectorAll(".module").forEach((m) => {
      m.classList.toggle("collapsed", collapse);
      m.querySelector(".mod-header").setAttribute("aria-expanded", String(!collapse));
    });
    syncCollapseAll();
  });
})();
