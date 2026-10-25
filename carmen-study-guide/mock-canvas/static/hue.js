// Hue, the course assistant docked on every course page (ui.hue_dock): a chat box at the side that shows
// "Analyze goals" answers and opens into the study tutor window. Hue's text is model output: render it with
// textContent only, never innerHTML.
(() => {
  const root = document.getElementById("hue");
  if (!root) return;
  const course = encodeURIComponent(root.dataset.course);
  const byId = (id) => document.getElementById(id);
  const box = byId("hue-box"), launcher = byId("hue-launcher"), log = byId("hue-log");
  const expandBtn = byId("hue-expand"), closeBtn = byId("hue-close");
  const status = byId("hue-status"), signinBtn = byId("hue-signin"), loginForm = byId("hue-login");
  const select = byId("hue-assessment"), signout = byId("hue-signout");
  const form = byId("hue-form"), input = byId("hue-input"), send = form.querySelector("button");
  const MODES = {
    protected_assessment: "Protected: concept help only",
    guided_homework: "Guided: hints, not answers",
    independent_study: "Independent study",
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
  let contextLoaded = false;
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
    if (open && !contextLoaded) {
      contextLoaded = true;
      loadContext().catch(() => setSignedIn(false));
    }
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
    (signedIn ? input : closeBtn).focus();
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

  // ---- study tutor: sign-in, what the student is working on, and the chat (tutor/router.py)
  let signedIn = false;
  let authGeneration = 0;
  let sessionId = null;
  let generation = 0; // bumped on context switch so late replies from the old context are dropped

  function setSignedIn(value) {
    signedIn = value;
    generation++; sessionId = null;
    log.querySelectorAll(".hue-chat").forEach((n) => n.remove()); // tutor turns belong to the signed-in student
    root.classList.toggle("is-signed-in", value);
    send.disabled = !value;
    status.textContent = "";
  }
  async function loadContext() {
    const requested = ++authGeneration;
    const res = await fetch(`/courses/${course}/tutor/context`, { cache: "no-store" });
    if (requested !== authGeneration) return;
    if (!res.ok) { setSignedIn(false); return; }
    const data = await res.json();
    if (requested !== authGeneration) return;
    setSignedIn(true);
    select.replaceChildren(new Option("General study (no assignment)", ""));
    for (const a of data.assessments) select.add(new Option(`${a.title} (${MODES[a.mode]})`, a.id));
  }
  signinBtn.addEventListener("click", () => {
    setExpanded(true);
    loginForm.querySelector("input").focus();
  });
  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    authGeneration++;
    const values = new FormData(loginForm);
    const button = loginForm.querySelector("button");
    button.disabled = true;
    const body = JSON.stringify({ email: values.get("email"), password: values.get("password") });
    loginForm.reset();
    try {
      const res = await fetch(`/courses/${course}/tutor/auth/login`, {
        method: "POST", headers: { "Content-Type": "application/json", "X-Tutor-Request": "1" }, body,
      });
      if (!res.ok) throw new Error();
      await loadContext();
      if (signedIn) input.focus();
      else status.textContent = "This account needs a course enrollment and learner identity mapping.";
    } catch { status.textContent = "Sign-in failed. Check your course account and configuration."; }
    finally { button.disabled = false; }
  });
  signout.addEventListener("click", async () => {
    authGeneration++;
    setSignedIn(false);
    try {
      const res = await fetch(`/courses/${course}/tutor/auth/logout`, { method: "POST", headers: { "X-Tutor-Request": "1" } });
      if (!res.ok) throw new Error();
    } catch {
      root.classList.add("is-signed-in");
      status.textContent = "Sign-out failed. Retry signing out before leaving this browser.";
    }
  });
  select.addEventListener("change", () => {
    generation++; sessionId = null;
    add(el("div", "hue-divider hue-chat", `Now helping with: ${select.selectedOptions[0].text}`));
  });

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
  function addTutor(data) {
    const msg = el("div", "hue-msg hue-bot hue-chat");
    msg.append(el("span", `hue-mode hue-mode-${data.mode}`, MODES[data.mode] || data.mode));
    msg.append(el("p", "hue-text", data.message));
    if (data.next_step) msg.append(el("p", "hue-next", `Next: ${data.next_step}`));
    if (data.citations?.length) {
      const list = el("ul", "hue-cites");
      for (const c of data.citations) {
        const li = el("li");
        const label = `${c.title} (${c.location})`;
        // Only links to this site: a link from data must never become javascript: or an external URL.
        const href = sameSite(c.deep_link);
        if (href) {
          const a = el("a", null, label);
          a.href = href;
          li.append(a);
        } else {
          li.textContent = label;
        }
        list.append(li);
      }
      msg.append(list);
    }
    if (data.fallback) msg.append(el("p", "hue-note", "Hue gave a safe default answer this time."));
    add(msg);
  }
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const message = input.value.trim();
    if (!message || send.disabled) return;
    const sent = generation;
    send.disabled = true;
    add(el("div", "hue-msg hue-me hue-chat", message));
    input.value = "";
    try {
      const res = await fetch(`/courses/${course}/tutor/turn`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Tutor-Request": "1" },
        body: JSON.stringify({ message, session_id: sessionId, assessment_id: select.value || null }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (res.status === 401) setSignedIn(false);
        const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join("; ") : data.detail;
        throw new Error(detail || `Request failed (${res.status})`);
      }
      if (sent !== generation) return; // the student switched assessments while this was in flight
      sessionId = data.session_id;
      addTutor(data);
    } catch (err) {
      if (sent === generation) add(el("div", "hue-msg hue-error hue-chat", err.message));
    } finally {
      send.disabled = !signedIn;
      input.focus();
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
  setSignedIn(false);
  let saved = {};
  try { saved = JSON.parse(sessionStorage.getItem("hue") || "{}"); } catch { /* storage off */ }
  if (root.dataset.open === "expanded") saved = { open: true, expanded: true };
  setExpanded(Boolean(saved.expanded));
  setOpen(Boolean(saved.open));
})();
