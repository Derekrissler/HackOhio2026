// Study Tutor chat. Tutor text is model output: it is only ever set with textContent (formatting builds
// elements, never HTML), and links are limited to this site.
(() => {
  const root = document.querySelector(".tutor");
  if (!root) return;
  const course = root.dataset.course;
  const $ = (id) => document.getElementById(id);
  const signinView = $("tutor-signin"), chatView = $("tutor-chat");
  const loginForm = $("tutor-login-form"), signinError = $("tutor-signin-error");
  const signout = $("tutor-signout"), select = $("tutor-assessment"), banner = $("tutor-mode-banner");
  const log = $("tutor-log"), form = $("tutor-form"), input = $("tutor-input");
  const sendButton = form.querySelector("button");
  const who = root.querySelector(".tutor-who"), avatar = root.querySelector(".tutor-avatar");
  // Demo mode: the tutor uses Carmen's signed-in student automatically; Carmen's Account > Logout signs out of both.
  const demoOn = root.dataset.demo === "1";
  const loading = $("tutor-loading");
  if (demoOn) signout.hidden = true;
  const api = (path) => `/courses/${encodeURIComponent(course)}/tutor${path}`;

  const MODES = {
    protected_assessment: {
      label: "Protected: concept help only",
      explain: "This work is open and graded. The tutor will explain the ideas behind it and point you to the " +
               "slides, but won't help with its questions or answers.",
    },
    guided_homework: {
      label: "Guided: hints, not answers",
      explain: "You'll get guiding questions and step-by-step hints. The tutor won't write your answers for you.",
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

  let assessments = [], signedIn = false, sessionId = null;
  let generation = 0, authGeneration = 0; // bumped to drop replies that arrive after a context switch

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  };

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

  // ---------------------------------------------------------------- formatting (safe subset of markdown)

  function inline(text) {
    const frag = document.createDocumentFragment();
    for (const part of text.split(/(\*\*[^*]+\*\*|`[^`]+`)/)) {
      if (/^\*\*[^*]+\*\*$/.test(part)) frag.append(el("strong", null, part.slice(2, -2)));
      else if (/^`[^`]+`$/.test(part)) frag.append(el("code", null, part.slice(1, -1)));
      else if (part) frag.append(document.createTextNode(part));
    }
    return frag;
  }

  function rich(text) {
    const out = el("div", "tutor-text");
    let list = null, para = null;
    for (const raw of String(text).split("\n")) {
      const line = raw.trimEnd();
      const item = line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/);
      if (item) {
        const ordered = /^\s*\d/.test(line);
        if (!list || list.tagName !== (ordered ? "OL" : "UL")) { list = el(ordered ? "ol" : "ul"); out.append(list); }
        const li = el("li"); li.append(inline(item[1])); list.append(li);
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

  // ---------------------------------------------------------------- views

  function showSignedIn(user) {
    signedIn = true;
    loading.hidden = true;
    signinView.hidden = true;
    chatView.hidden = false;
    const name = user?.name || user?.email || "your course account";
    who.textContent = "";
    who.append("Signed in as ", el("strong", null, name), user?.email && user?.name ? ` · ${user.email}` : "");
    if (user?.email?.endsWith("@demo.test")) who.append(el("span", "tutor-demo-tag", "demo mode"));
    avatar.textContent = (name.match(/\b\w/g) || ["✓"]).slice(0, 2).join("").toUpperCase();
    input.focus();
  }

  function showSignedOut(message) {
    signedIn = false;
    generation++; sessionId = null;
    if (demoOn) { showUnavailable(message || "The tutor couldn't start."); return; } // demo mode never shows the form
    loading.hidden = true;
    chatView.hidden = true;
    signinView.hidden = false;
    signinError.hidden = !message;
    signinError.textContent = message || "";
  }

  function showUnavailable(message) {
    chatView.hidden = true;
    signinView.hidden = true;
    loading.hidden = false;
    loading.textContent = `${message} Refresh the page to try again.`;
  }

  async function demoSignIn() {
    const res = await fetch(api("/auth/demo"), { method: "POST", headers: { "X-Tutor-Request": "1" } });
    if (res.status === 401) { location.href = "/logged-out"; return false; } // logged out of Carmen
    if (!res.ok) {
      const detail = await res.json().then((d) => (typeof d.detail === "string" ? d.detail : ""), () => "");
      showUnavailable(`${detail || `The tutor couldn't start (${res.status})`}.`);
      return false;
    }
    return loadContext();
  }

  function currentMode() {
    const a = assessments.find((x) => x.id === select.value);
    return a ? a.mode : "independent_study";
  }

  function resetConversation() {
    generation++; sessionId = null;
    const mode = currentMode();
    banner.className = `tutor-banner tutor-banner-${mode}`;
    banner.textContent = "";
    banner.append(el("strong", null, MODES[mode].label), ` · ${MODES[mode].explain}`);
    log.replaceChildren(emptyState(mode));
  }

  function emptyState(mode) {
    const box = el("div", "tutor-empty");
    box.append(el("p", null, "Try asking:"));
    const chips = el("div", "tutor-chips");
    for (const q of SUGGESTIONS[mode]) {
      const chip = el("button", "tutor-chip", q);
      chip.type = "button";
      chip.addEventListener("click", () => { input.value = q; form.requestSubmit(); });
      chips.append(chip);
    }
    box.append(chips);
    return box;
  }

  async function loadContext(quiet = false) {
    const requested = ++authGeneration;
    const res = await fetch(api("/context"), { cache: "no-store" });
    if (requested !== authGeneration) return false;
    if (!res.ok) {
      // quiet: the caller decides what to show next (e.g. the demo sign-in), so nothing flashes on screen.
      if (!quiet) showSignedOut(res.status === 403 ? "This account isn't linked to a student in this course." : "");
      return false;
    }
    const data = await res.json();
    if (requested !== authGeneration) return false;
    assessments = data.assessments || [];
    select.replaceChildren(new Option("General study (no assignment)", ""));
    for (const a of assessments) select.add(new Option(`${a.title} (${MODES[a.mode]?.label || a.mode})`, a.id));
    const wanted = assessments.find((a) => a.canvas_id && a.canvas_id === root.dataset.assignment);
    if (wanted) select.value = wanted.id;
    showSignedIn(data.user);
    resetConversation();
    return true;
  }

  // ---------------------------------------------------------------- sign in / out

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    authGeneration++;
    const values = new FormData(loginForm);
    const button = loginForm.querySelector("button");
    button.disabled = true;
    button.textContent = "Signing in…";
    signinError.hidden = true;
    const body = JSON.stringify({ email: String(values.get("email")).trim(), password: values.get("password") });
    try {
      const res = await fetch(api("/auth/login"), {
        method: "POST", headers: { "Content-Type": "application/json", "X-Tutor-Request": "1" }, body,
      });
      if (!res.ok) {
        // The server says which part failed: credentials (401), rate limit (429) or its own setup (503).
        const detail = await res.json().then((d) => (typeof d.detail === "string" ? d.detail : ""), () => "");
        const fallback = { 401: "Wrong email or password", 429: "Too many sign-in attempts. Wait a minute and try again" };
        throw new Error(`${detail || fallback[res.status] || `Sign-in failed (${res.status})`}.`);
      }
      loginForm.reset();
      await loadContext();
    } catch (err) {
      showSignedOut(err.message || "Sign-in failed. Is the tutor server running?");
    } finally {
      button.disabled = false;
      button.textContent = "Sign in";
    }
  });

  signout.addEventListener("click", async () => {
    authGeneration++;
    signout.disabled = true;
    try {
      const res = await fetch(api("/auth/logout"), { method: "POST", headers: { "X-Tutor-Request": "1" } });
      if (!res.ok) throw new Error();
      showSignedOut("");
    } catch {
      who.textContent = "Sign-out failed. Try again before leaving this computer.";
    } finally {
      signout.disabled = false;
    }
  });

  select.addEventListener("change", resetConversation);

  // ---------------------------------------------------------------- chat

  function scrollDown() { log.scrollTop = log.scrollHeight; }

  function addStudent(text) {
    log.querySelector(".tutor-empty")?.remove();
    log.append(el("div", "tutor-msg tutor-student", text));
    scrollDown();
  }

  function addThinking() {
    const bubble = el("div", "tutor-msg tutor-bot tutor-thinking");
    bubble.setAttribute("aria-label", "Tutor is thinking");
    bubble.append(el("span", "tutor-dots", "Tutor is thinking"));
    log.append(bubble);
    scrollDown();
    return bubble;
  }

  function addTutor(data) {
    const box = el("div", "tutor-msg tutor-bot");
    box.append(el("span", `tutor-mode tutor-mode-${data.mode}`, MODES[data.mode]?.label || data.mode));
    box.append(rich(data.message));
    const quoted = new Set();
    for (const s of data.snippets || []) {
      quoted.add(s.chunk_id);
      const card = el("figure", "tutor-snippet");
      card.append(el("blockquote", null, s.text));
      const caption = el("figcaption", null, `${s.title} · ${s.location}`);
      const href = sameSite(s.deep_link);
      if (href) {
        const open = el("a", "tutor-snippet-open", s.location.startsWith("slide") ? "Open slide ↗" : "Open page ↗");
        open.href = href;
        open.target = "_blank";
        open.rel = "noopener";
        caption.append(" ", open);
      }
      card.append(caption);
      box.append(card);
    }
    if (data.next_step) {
      const next = el("p", "tutor-next");
      next.append(el("strong", null, "Next step: "), inline(data.next_step));
      box.append(next);
    }
    const sources = (data.citations || []).filter((c) => !quoted.has(c.id));
    if (sources.length) {
      const wrap = el("div", "tutor-sources");
      wrap.append(el("span", "muted small", "Sources: "));
      sources.forEach((c, i) => {
        const href = sameSite(c.deep_link);
        const label = `${c.title} (${c.location})`;
        // Only links to this site: a link from data must never become javascript: or an external URL.
        const node = href ? Object.assign(el("a", null, label), { href, target: "_blank", rel: "noopener" }) : el("span", null, label);
        wrap.append(node, i < sources.length - 1 ? " · " : "");
      });
      box.append(wrap);
    }
    if (data.fallback) {
      box.append(el("p", "tutor-note muted small", "Showing a safe default answer. Try rephrasing your question."));
    }
    log.append(box);
    scrollDown();
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const message = input.value.trim();
    if (!message || sendButton.disabled || !signedIn) return;
    const sent = generation;
    sendButton.disabled = true;
    sendButton.textContent = "Sending…";
    addStudent(message);
    input.value = "";
    const thinking = addThinking();
    try {
      const res = await fetch(api("/turn"), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Tutor-Request": "1" },
        body: JSON.stringify({ message, session_id: sessionId, assessment_id: select.value || null }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (res.status === 401 && demoOn) {
          // The tutor session expired (or Carmen logged out): reconnect quietly, then ask the student to resend.
          if (await demoSignIn()) throw new Error("Reconnected to the tutor. Please send your message again.");
          return;
        }
        if (res.status === 401) { showSignedOut("Your session expired. Sign in again."); return; }
        const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join("; ") : data.detail;
        throw new Error(detail || `Request failed (${res.status})`);
      }
      if (sent !== generation) return; // the student switched assessments while this was in flight
      sessionId = data.session_id;
      addTutor(data);
    } catch (err) {
      if (sent === generation) log.append(el("div", "tutor-msg tutor-error", err.message));
    } finally {
      thinking.remove();
      sendButton.disabled = false;
      sendButton.textContent = "Send";
      if (signedIn) input.focus();
    }
  });

  input.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
    e.preventDefault();
    if (!sendButton.disabled) form.requestSubmit();
  });

  // Startup: reuse an existing session; otherwise demo sign-in (unless this browser signed out); otherwise the form.
  loadContext(true)
    .then((ok) => {
      if (ok) return;
      if (demoOn) return demoSignIn();
      showSignedOut("");
    })
    .catch(() => showSignedOut(""));
})();
