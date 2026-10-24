// Study Tutor chat. Tutor text is model output: render it with textContent only, never innerHTML.
(() => {
  const root = document.querySelector(".tutor");
  if (!root) return;
  const course = root.dataset.course;
  const log = document.getElementById("tutor-log");
  const form = document.getElementById("tutor-form");
  const input = document.getElementById("tutor-input");
  const select = document.getElementById("tutor-assessment");
  const MODES = {
    protected_assessment: "Protected: concept help only",
    guided_homework: "Guided: hints, not answers",
    independent_study: "Independent study",
  };
  let sessionId = null;
  let generation = 0; // bumped on context switch so late replies from the old context are dropped

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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, session_id: sessionId, assessment_id: select.value || null }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join("; ") : data.detail;
        throw new Error(detail || `Request failed (${res.status})`);
      }
      if (sent !== generation) return; // the student switched assessments while this was in flight
      sessionId = data.session_id;
      addTutor(data);
    } catch (err) {
      if (sent === generation) log.append(el("div", "tutor-msg tutor-error", err.message));
    } finally {
      button.disabled = false;
      input.focus();
    }
  });

  input.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
    e.preventDefault();
    if (!form.querySelector("button").disabled) form.requestSubmit();
  });
})();
