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

  // ---- Database sync: every page load mirrors the course into Supabase (sync.py), shown in the header
  const SYNC_TEXT = {
    syncing: ["busy", "Syncing to database…"],
    synced: ["ok", "Database synced"],
    up_to_date: ["ok", "Database up to date"],
    not_configured: ["", "Database sync off (no service key)"],
    failed: ["err", "Database sync failed"],
  };
  function showSync(badge, st) {
    const [cls, text] = SYNC_TEXT[st.status] || ["", st.status];
    badge.className = `sync-status ${cls}`;
    badge.textContent = text;
    badge.title = st.error || (st.finished_at ? `Last finished ${new Date(st.finished_at).toLocaleTimeString()}` : "");
  }
  document.querySelectorAll("[data-sync]").forEach(async (badge) => {
    const url = badge.dataset.sync;
    try {
      let st = await (await fetch(url, { method: "POST" })).json();
      showSync(badge, st);
      for (let i = 0; st.running && i < 120; i++) {  // poll up to ~3 minutes
        await new Promise((r) => setTimeout(r, 1500));
        st = await (await fetch(url)).json();
        showSync(badge, st);
      }
    } catch (err) {
      showSync(badge, { status: "failed", error: String(err) });
    }
  });

  // ---- "Export for analytics": builds the ingestion bundle server-side (ingest.py)
  const exportBtn = document.getElementById("export-btn");
  const exportPanel = document.getElementById("export-panel");
  function el(tag, text, cls) {
    const e = document.createElement(tag);
    if (text != null) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  }
  exportBtn?.addEventListener("click", async () => {
    const labelEl = exportBtn.querySelector("span");
    const label = labelEl.textContent;
    exportBtn.disabled = true;
    labelEl.textContent = " Exporting…";
    exportPanel.replaceChildren(el("p", "Pulling this assessment's grades, feedback and related material from Canvas…", "muted"));
    exportPanel.hidden = false;
    try {
      const res = await fetch(exportBtn.dataset.url, { method: "POST" });
      if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
      const d = await res.json();
      const counts = el("dl");
      for (const [k, v] of Object.entries(d.counts)) counts.append(el("dt", k.replace(/_/g, " ")), el("dd", String(v)));
      const download = el("a", "Download JSON");
      download.href = d.download_url;
      download.className = "btn";
      const parts = [el("h3", d.database?.status === "stored" ? "Exported and stored" : "Export ready"),
                     el("div", d.scope?.assessment_name || d.export_id, "muted small"), counts];
      if (d.related.length) {
        const ul = el("ul", null, "related");
        d.related.forEach((r) => {
          const li = el("li", r.title);
          if (r.why.length) li.append(el("div", r.why.join(" · "), "why"));
          ul.append(li);
        });
        parts.push(el("div", `Related material (${d.related.length})`, "small"), ul);
      }
      if (d.warnings.length) {
        const ul = el("ul");
        d.warnings.forEach((w) => ul.append(el("li", w)));
        parts.push(el("div", "Notes", "small"), ul);
      }
      const saved = el("p", "Saved to ", "small muted");
      saved.append(el("code", `mock-canvas/${d.path}`));
      const db = d.database || {};
      let dbLine;
      if (db.status === "stored") {
        const n = Object.entries(db.rows_written).filter(([k]) => k !== "files_uploaded")
          .reduce((sum, [, v]) => sum + v, 0);
        dbLine = el("p", `Synced to database: ${n} rows checked or updated, ${db.rows_written.files_uploaded || 0} files stored. Re-exporting doesn't create duplicates.`, "small");
      } else if (db.status === "skipped") {
        dbLine = el("p", `Database: skipped (${db.reason}).`, "small muted");
      } else {
        dbLine = el("p", `Database write failed: ${db.error}`, "small err");
      }
      parts.push(dbLine, saved, download);
      exportPanel.replaceChildren(...parts);
    } catch (err) {
      exportPanel.replaceChildren(el("h3", "Export failed"), el("p", String(err), "err"));
    } finally {
      exportBtn.disabled = false;
      labelEl.textContent = label;
    }
  });
  document.addEventListener("click", (e) => {
    if (exportPanel && !exportPanel.hidden && !e.target.closest(".export-wrap")) exportPanel.hidden = true;
  });

  // ---- "Analyze goals": Claude proposes outcome weights for one question (claude_mapper.py)
  document.querySelectorAll(".goal-btn").forEach((btn) => {
    const panel = btn.parentElement.querySelector(".goal-panel");
    btn.addEventListener("click", async () => {
      const labelEl = btn.querySelector("span");
      const label = labelEl.textContent;
      btn.disabled = true;
      labelEl.textContent = "Asking Claude…";
      panel.replaceChildren(el("p", "Claude is reading the course materials and outcomes (about 10–30 seconds)…", "muted small"));
      panel.hidden = false;
      try {
        const res = await fetch(btn.dataset.goals, { method: "POST" });
        const d = await res.json();
        if (!res.ok) throw new Error(d.message || d.detail || res.status);
        const list = el("ul", null, "goal-list");
        d.mappings.forEach((m) => {
          const li = el("li");
          const pct = Math.round(m.weight * 100);
          const head = el("div", null, "goal-head");
          head.append(el("b", m.outcome), el("span", `${pct}%`, "goal-pct"));
          const bar = el("div", null, "goal-bar");
          bar.append(el("i"));
          bar.firstChild.style.width = `${pct}%`;
          li.append(head, bar);
          if (m.text) li.append(el("div", m.text, "small muted"));
          if (m.reason) li.append(el("p", m.reason, "small"));
          if (m.sources?.length) li.append(el("div", `Sources: ${m.sources.join(" · ")}`, "small muted"));
          list.append(li);
        });
        const note = d.status === "kept"
          ? d.message
          : `Saved as a suggestion for review · ${d.model} · confidence ${Math.round(d.confidence * 100)}% · ${d.lers.lers_created} analysis records updated`;
        panel.replaceChildren(list, el("p", note, "small muted"));
      } catch (err) {
        panel.replaceChildren(el("p", String(err.message || err), "small err"));
      } finally {
        btn.disabled = false;
        labelEl.textContent = label;
      }
    });
  });
  document.addEventListener("click", (e) => {
    document.querySelectorAll(".goal-panel:not([hidden])").forEach((p) => {
      if (!p.parentElement.contains(e.target)) p.hidden = true;
    });
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
