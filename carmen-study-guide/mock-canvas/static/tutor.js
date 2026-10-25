// Study Tutor chat. Tutor text is model output: render it with textContent only, never innerHTML.
(() => {
  const root = document.querySelector(".tutor");
  if (!root) return;
  const course = root.dataset.course;
  const log = document.getElementById("tutor-log");
  const form = document.getElementById("tutor-form");
  const input = document.getElementById("tutor-input");
  const select = document.getElementById("tutor-assessment");
  const loginForm = document.getElementById("tutor-login-form");
  const signout = document.getElementById("tutor-signout");
  const notice = root.querySelector(".tutor-notice");
  let signedIn = false;
  let authGeneration = 0;
  const MODES = {
    protected_assessment: "Protected: concept help only",
    guided_homework: "Guided: hints, not answers",
    independent_study: "Independent study",
  };
  let sessionId = null;
  let generation = 0; // bumped on context switch so late replies from the old context are dropped

  function setSignedIn(value) {
    signedIn = value;
    generation++; sessionId = null; log.replaceChildren();
    loginForm.hidden = value; signout.hidden = !value;
    form.querySelector("button").disabled = !value;
    select.disabled = !value;
    notice.textContent = value ? "Signed in to your course account." : "Sign in with your Supabase course account to use the tutor.";
  }
  async function loadContext() {
    const requested = ++authGeneration;
    const res = await fetch(`/courses/${encodeURIComponent(course)}/tutor/context`, { cache: "no-store" });
    if (requested !== authGeneration) return;
    if (!res.ok) { setSignedIn(false); return; }
    const data = await res.json();
    if (requested !== authGeneration) return;
    setSignedIn(true);
    select.replaceChildren(new Option("General study (no assignment)", ""));
    for (const a of data.assessments) select.add(new Option(`${a.title} (${MODES[a.mode]})`, a.id));
  }
  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    authGeneration++;
    const values = new FormData(loginForm);
    const button = loginForm.querySelector("button");
    button.disabled = true;
    const body = JSON.stringify({ email: String(values.get("email")).trim(), password: values.get("password") });
    loginForm.reset();
    try {
      const res = await fetch(`/courses/${encodeURIComponent(course)}/tutor/auth/login`, {
        method: "POST", headers: { "Content-Type": "application/json", "X-Tutor-Request": "1" }, body,
      });
      if (!res.ok) {
        // The server says which part failed: credentials (401), rate limit (429) or its own setup (503).
        const detail = await res.json().then((d) => (typeof d.detail === "string" ? d.detail : ""), () => "");
        const fallback = { 401: "Wrong email or password.", 429: "Too many sign-in attempts. Wait a minute and try again." };
        throw new Error(detail ? `${detail}.` : fallback[res.status] || `Sign-in failed (${res.status}).`);
      }
      await loadContext();
      if (!signedIn) notice.textContent = "This account needs a course enrollment and learner identity mapping.";
    } catch (err) { notice.textContent = err.message || "Sign-in failed. Is the tutor server running?"; }
    finally { button.disabled = false; }
  });
  signout.addEventListener("click", async () => {
    authGeneration++;
    setSignedIn(false);
    try {
      const res = await fetch(`/courses/${encodeURIComponent(course)}/tutor/auth/logout`, {
        method: "POST", headers: { "X-Tutor-Request": "1" },
      });
      if (!res.ok) throw new Error();
    } catch {
      signout.hidden = false;
      notice.textContent = "Sign-out failed. Retry signing out before leaving this browser.";
    }
  });
  setSignedIn(false);
  loadContext().catch(() => setSignedIn(false));

  select.addEventListener("change", () => { generation++; sessionId = null; log.replaceChildren(); });

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
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

  function addStudent(text) {
    log.append(el("div", "tutor-msg tutor-student", text));
    log.scrollTop = log.scrollHeight;
  }

  function addTutor(data) {
    const box = el("div", "tutor-msg tutor-bot");
    box.append(el("span", `tutor-mode tutor-mode-${data.mode}`, MODES[data.mode] || data.mode));
    box.append(el("p", "tutor-text", data.message));
    for (const s of data.snippets || []) {
      const card = el("figure", "tutor-snippet");
      card.append(el("blockquote", null, s.text));
      const caption = el("figcaption", null, `${s.title} · ${s.location}`);
      const href = sameSite(s.deep_link);
      if (href) {
        const open = el("a", "tutor-snippet-open", s.location.startsWith("slide") ? "Open slide" : "Open page");
        open.href = href;
        open.target = "_blank";
        open.rel = "noopener";
        caption.append(" ", open);
      }
      card.append(caption);
      box.append(card);
    }
    if (data.next_step) box.append(el("p", "tutor-next", `Next: ${data.next_step}`));
    if (data.citations?.length) {
      const list = el("ul", "tutor-cites");
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
      box.append(list);
    }
    if (data.fallback) box.append(el("p", "tutor-note muted small", "The tutor gave a safe default answer this time."));
    log.append(box);
    log.scrollTop = log.scrollHeight;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const message = input.value.trim();
    const button = form.querySelector("button");
    if (!message || button.disabled) return;
    const sent = generation;
    button.disabled = true;
    addStudent(message);
    input.value = "";
    try {
      const res = await fetch(`/courses/${encodeURIComponent(course)}/tutor/turn`, {
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
      if (sent === generation) log.append(el("div", "tutor-msg tutor-error", err.message));
    } finally {
      button.disabled = !signedIn;
      input.focus();
    }
  });

  input.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
    e.preventDefault();
    if (!form.querySelector("button").disabled) form.requestSubmit();
  });
})();
