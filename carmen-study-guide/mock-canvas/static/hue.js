// Hue, the course assistant docked on every course page (ui.hue_dock): a chat box at the side that shows
// "Analyze goals" answers and opens into the study tutor window. Hue's text is model output: it is only ever set
// with textContent (formatting builds elements, never HTML), and links are limited to this site.
//
// Students sign in to Carmen before it opens, so Hue never asks for a password: it reuses that course session, and in
// demo mode (data-demo, TUTOR_DEMO_AUTO_SIGNIN) asks the server to start it.
(() => {
  const root = document.getElementById("hue");
  if (!root) return;
  const course = encodeURIComponent(root.dataset.course);
  const api = (path) => `/courses/${course}/tutor${path}`;
  const demoOn = root.dataset.demo === "1";
  const byId = (id) => document.getElementById(id);
  const box = byId("hue-box"), launcher = byId("hue-launcher"), log = byId("hue-log");
  const expandBtn = byId("hue-expand"), closeBtn = byId("hue-close");
  const status = byId("hue-status"), select = byId("hue-assessment"), banner = byId("hue-banner");
  const form = byId("hue-form"), input = byId("hue-input"), send = form.querySelector("button");
  const MODES = {
    protected_assessment: {
      label: "Protected: concept help only",
      explain: "This work is open and graded. Hue will explain the ideas behind it and point you to the slides, " +
               "but won't help with its questions or answers.",
    },
    guided_homework: {
      label: "Guided: hints, not answers",
      explain: "You'll get guiding questions and step-by-step hints. Hue won't write your answers for you.",
    },
    independent_study: {
      label: "Independent study",
      explain: "Full explanations and examples from the course material.",
    },
  };
  const SUGGESTIONS = {
    independent_study: ["What does lecture 2 say a good prompt needs?", "What is vibe coding, according to the slides?",
                        "How should I review code an AI wrote for me?"],
    guided_homework: ["Where should I start?", "Which slides cover this?", "Can you give me a small hint?"],
    protected_assessment: ["Which slides cover the ideas behind this?", "Can you explain the main concept here?"],
  };

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }
  function add(node) {
    log.append(node);
    log.scrollTop = log.scrollHeight;
    return node;
  }

  // ---- open, close, expand. The state is remembered for this tab, so Hue stays put while you move between pages.
  let expanded = false;
  let connecting = null;
  function remember() {
    try { sessionStorage.setItem("hue", JSON.stringify({ open: !box.hidden, expanded })); } catch { /* storage off */ }
  }
  function sync() {
    // A docked tutor window pushes the page aside on wide screens instead of covering it (hue.css).
    document.body.classList.toggle("hue-docked", !box.hidden && expanded);
    remember();
  }
  function setOpen(open) {
    box.hidden = !open;
    launcher.hidden = open;
    launcher.setAttribute("aria-expanded", String(open));
    if (open && !connecting) connecting = connect();
    sync();
  }
  function setExpanded(value) {
    expanded = value;
    root.classList.toggle("is-expanded", value);
    expandBtn.setAttribute("aria-pressed", String(value));
    const label = value ? "Back to chat box" : "Open as tutor window";
    expandBtn.title = label;
    expandBtn.setAttribute("aria-label", label);
    sync();
  }
  launcher.addEventListener("click", () => {
    setOpen(true);
    (ready ? input : closeBtn).focus();
  });
  closeBtn.addEventListener("click", () => {
    setOpen(false);
    launcher.focus();
  });
  expandBtn.addEventListener("click", () => setExpanded(!expanded));
  box.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    setOpen(false);
    launcher.focus();
  });

  // ---- course session and what the student is working on (tutor_host.py, tutor/router.py)
  let ready = false;
  let assessments = [];
  let sessionId = null;
  let generation = 0; // bumped on context switch so late replies from the old context are dropped
  let contextGeneration = 0;

  function setReady(value, message = "") {
    ready = value;
    root.classList.toggle("is-ready", value);
    input.disabled = send.disabled = !value;
    status.textContent = message;
  }
  async function connect() {
    setReady(false, "Connecting to Hue…");
    try {
      const result = await loadContext();
      if (result === true) return;
      if (result === 401 && demoOn && await startDemoSession()) return;
      if (!ready && result !== "handled") unavailable(result === 403 ? "Your course account isn't linked to a student in this course." : "");
    } catch {
      unavailable("");
    }
  }
  function unavailable(message) {
    generation++; sessionId = null;
    setReady(false, `${message || "Hue can't reach your course session right now."} Refresh the page to try again.`);
  }
  async function startDemoSession() {
    const res = await fetch(api("/auth/demo"), { method: "POST", headers: { "X-Tutor-Request": "1" } });
    if (res.status === 401) { location.href = "/logged-out"; return false; } // logged out of Carmen
    if (!res.ok) {
      const detail = await res.json().then((d) => (typeof d.detail === "string" ? d.detail : ""), () => "");
      unavailable(detail ? `${detail}.` : `Hue couldn't start (${res.status}).`);
      return false;
    }
    return (await loadContext()) === true;
  }
  // true when connected; otherwise the HTTP status, so connect() can decide what to do next.
  async function loadContext() {
    const requested = ++contextGeneration;
    const res = await fetch(api("/context"), { cache: "no-store" });
    if (requested !== contextGeneration) return "handled";
    if (!res.ok) return res.status;
    const data = await res.json();
    if (requested !== contextGeneration) return "handled";
    assessments = data.assessments || [];
    select.replaceChildren(new Option("General study (no assignment)", ""));
    for (const a of assessments) select.add(new Option(`${a.title} (${MODES[a.mode]?.label || a.mode})`, a.id));
    // Preselect the assignment this page is about (or ?assignment= on the Hue page).
    const wanted = assessments.find((a) => a.canvas_id && String(a.canvas_id) === root.dataset.assignment);
    if (wanted) select.value = wanted.id;
    setReady(true);
    startConversation(false);
    return true;
  }
  function currentMode() {
    return assessments.find((a) => a.id === select.value)?.mode || "independent_study";
  }
  function startConversation(announce) {
    generation++; sessionId = null;
    const mode = currentMode();
    banner.className = `hue-banner hue-banner-${mode} hue-when-ready hue-when-expanded`;
    banner.replaceChildren(el("strong", null, MODES[mode].label), ` · ${MODES[mode].explain}`);
    log.querySelector(".hue-suggest")?.remove();
    if (announce) add(el("div", "hue-divider", `Now helping with: ${select.selectedOptions[0].text}`));
    add(suggestions(mode));
  }
  function suggestions(mode) {
    const wrap = el("div", "hue-suggest");
    wrap.append(el("p", null, "Try asking:"));
    for (const q of SUGGESTIONS[mode]) {
      const chip = el("button", "hue-chip", q);
      chip.type = "button";
      chip.addEventListener("click", () => { input.value = q; form.requestSubmit(); });
      wrap.append(chip);
    }
    return wrap;
  }
  select.addEventListener("change", () => startConversation(true));

  // ---- formatting: a safe subset of markdown, built as elements
  function inline(text) {
    const frag = document.createDocumentFragment();
    for (const part of String(text).split(/(\*\*[^*]+\*\*|`[^`]+`)/)) {
      if (/^\*\*[^*]+\*\*$/.test(part)) frag.append(el("strong", null, part.slice(2, -2)));
      else if (/^`[^`]+`$/.test(part)) frag.append(el("code", null, part.slice(1, -1)));
      else if (part) frag.append(document.createTextNode(part));
    }
    return frag;
  }
  function rich(text) {
    const out = el("div", "hue-text");
    let list = null, para = null;
    for (const raw of String(text).split("\n")) {
      const line = raw.trimEnd();
      const item = line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/);
      if (item) {
        const ordered = /^\s*\d/.test(line);
        if (!list || list.tagName !== (ordered ? "OL" : "UL")) { list = el(ordered ? "ol" : "ul"); out.append(list); }
        const li = el("li");
        li.append(inline(item[1]));
        list.append(li);
        para = null;
      } else if (!line.trim()) {
        list = null; para = null;
      } else {
        list = null;
        if (!para) { para = el("p"); out.append(para); } else para.append(document.createElement("br"));
        para.append(inline(line));
      }
    }
    return out;
  }
  function sameSite(link) {
    if (typeof link !== "string") return null;
    try {
      const url = new URL(link, location.origin);
      // Exports store absolute URLs from the export host (e.g. http://localhost:8001); keep only the path part.
      const local = url.hostname === location.hostname || ["localhost", "127.0.0.1"].includes(url.hostname);
      return url.protocol.startsWith("http") && local ? url.pathname + url.search + url.hash : null;
    } catch {
      return null;
    }
  }

  // ---- chat
  function addTutor(data) {
    const msg = el("div", "hue-msg hue-bot");
    msg.append(el("span", `hue-mode hue-mode-${data.mode}`, MODES[data.mode]?.label || data.mode));
    msg.append(rich(data.message));
    const quoted = new Set();
    for (const s of data.snippets || []) {
      quoted.add(s.chunk_id);
      const card = el("figure", "hue-snippet");
      card.append(el("blockquote", null, s.text));
      const caption = el("figcaption", null, `${s.title} · ${s.location}`);
      const href = sameSite(s.deep_link);
      if (href) {
        const open = el("a", "hue-snippet-open", s.location.startsWith("slide") ? "Open slide ↗" : "Open page ↗");
        Object.assign(open, { href, target: "_blank", rel: "noopener" });
        caption.append(" ", open);
      }
      card.append(caption);
      msg.append(card);
    }
    if (data.next_step) {
      const next = el("p", "hue-next");
      next.append(el("strong", null, "Next step: "), inline(data.next_step));
      msg.append(next);
    }
    const sources = (data.citations || []).filter((c) => !quoted.has(c.id));
    if (sources.length) {
      const wrap = el("p", "hue-note");
      wrap.append("Sources: ");
      sources.forEach((c, i) => {
        // Only links to this site: a link from data must never become javascript: or an external URL.
        const href = sameSite(c.deep_link);
        const label = `${c.title} (${c.location})`;
        wrap.append(href ? Object.assign(el("a", null, label), { href, target: "_blank", rel: "noopener" }) : label,
                    i < sources.length - 1 ? " · " : "");
      });
      msg.append(wrap);
    }
    if (data.fallback) msg.append(el("p", "hue-note", "Showing a safe default answer. Try rephrasing your question."));
    add(msg);
  }
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const message = input.value.trim();
    if (!message || send.disabled || !ready) return;
    const sent = generation;
    send.disabled = true;
    log.querySelector(".hue-suggest")?.remove();
    add(el("div", "hue-msg hue-me", message));
    input.value = "";
    const thinking = add(el("div", "hue-msg hue-bot is-thinking"));
    thinking.append(el("span", "hue-dots", "Hue is thinking"));
    try {
      const res = await fetch(api("/turn"), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Tutor-Request": "1" },
        body: JSON.stringify({ message, session_id: sessionId, assessment_id: select.value || null }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (res.status === 401 && demoOn) {
          // The course session expired: reconnect quietly, then ask the student to resend.
          if (await startDemoSession()) throw new Error("Reconnected to Hue. Please send your message again.");
          return;
        }
        if (res.status === 401) { unavailable("Your course session has ended."); return; }
        const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join("; ") : data.detail;
        throw new Error(detail || `Request failed (${res.status})`);
      }
      if (sent !== generation) return; // the student switched assessments while this was in flight
      sessionId = data.session_id;
      addTutor(data);
    } catch (err) {
      if (sent === generation) add(el("div", "hue-msg hue-error", err.message));
    } finally {
      thinking.remove();
      send.disabled = !ready;
      if (ready) input.focus();
    }
  });
  input.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
    e.preventDefault();
    if (!send.disabled) form.requestSubmit();
  });

  // ---- "Analyze goals": the target icon on a question posts its outcome weights here (claude_mapper.py)
  document.querySelectorAll(".goal-btn").forEach((btn) => {
    let answer = null; // the message holding this question's latest answer
    btn.addEventListener("click", () => {
      setOpen(true);
      // Show the answer Hue already gave, since every run is a paid API call; "Run again" asks afresh.
      if (answer?.isConnected) return highlight(answer);
      analyze();
    });
    async function analyze() {
      if (btn.disabled) return;
      btn.disabled = true;
      btn.classList.add("is-busy");
      const what = `${btn.dataset.goal} · ${btn.dataset.goalTitle}`;
      add(el("div", "hue-msg hue-me", `Analyze goals: ${what}`));
      const msg = add(el("div", "hue-msg hue-bot is-thinking"));
      msg.append(el("p", null, "Reading the course materials and learning outcomes (about 10–30 seconds)…"));
      try {
        const res = await fetch(btn.dataset.goals, { method: "POST" });
        const d = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(d.message || d.detail || `Request failed (${res.status})`);
        const list = el("ul", "hue-goals");
        for (const m of d.mappings) {
          const li = el("li");
          const pct = Math.round(m.weight * 100);
          const head = el("div", "hue-goal-head");
          head.append(el("b", null, m.outcome), el("span", "hue-goal-pct", `${pct}%`));
          const bar = el("div", "hue-goal-bar");
          bar.append(el("i"));
          bar.firstChild.style.width = `${pct}%`;
          li.append(head, bar);
          if (m.text) li.append(el("div", "hue-note", m.text));
          if (m.reason) li.append(el("p", null, m.reason));
          if (m.sources?.length) li.append(el("div", "hue-note", `Sources: ${m.sources.join(" · ")}`));
          list.append(li);
        }
        const note = d.status === "kept"
          ? d.message
          : `Saved as a suggestion for review · confidence ${Math.round(d.confidence * 100)}% · ${d.lers.lers_created} analysis records updated`;
        const again = el("button", "hue-link", "Run again");
        again.type = "button";
        again.addEventListener("click", analyze);
        msg.replaceChildren(el("p", "hue-title", what), list, el("p", "hue-note", note), again);
        answer = msg;
        btn.classList.add("is-done");
      } catch (err) {
        msg.classList.add("hue-error");
        msg.replaceChildren(el("p", null, String(err.message || err)));
        answer = null;
        btn.classList.remove("is-done"); // so the next click retries
      } finally {
        msg.classList.remove("is-thinking");
        btn.disabled = false;
        btn.classList.remove("is-busy");
        log.scrollTop = log.scrollHeight;
      }
    }
  });
  function highlight(node) {
    node.scrollIntoView({ block: "nearest" });
    node.classList.remove("is-flash");
    void node.offsetWidth; // restart the animation
    node.classList.add("is-flash");
  }

  // ---- start: the Hue page opens as the tutor window; elsewhere, restore how this tab left Hue
  let saved = {};
  try { saved = JSON.parse(sessionStorage.getItem("hue") || "{}"); } catch { /* storage off */ }
  if (root.dataset.open === "expanded") saved = { open: true, expanded: true };
  setExpanded(Boolean(saved.expanded));
  setOpen(Boolean(saved.open));
})();
