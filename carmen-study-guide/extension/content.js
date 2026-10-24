// Runs on Canvas assignment pages. Reads the signed-in student's own graded feedback
// through the Canvas API (same-origin, uses their session), then asks the backend
// which course material to review.

(function () {
  const m = location.pathname.match(/\/courses\/(\d+)\/assignments\/(\d+)/);
  if (!m) return;
  const [, courseId, assignmentId] = m;

  const panel = createPanel();
  panel.setBody(`<button id="csg-run" class="csg-btn">Analyze my feedback</button>`);
  panel.el.querySelector("#csg-run").addEventListener("click", () => run(courseId, assignmentId, panel));
})();

async function run(courseId, assignmentId, panel) {
  panel.setBody(`<div class="csg-muted">Reading your feedback…</div>`);

  let feedback;
  try {
    feedback = await getFeedback(courseId, assignmentId);
  } catch (e) {
    return panel.setBody(`<div class="csg-err">Couldn't read feedback from Canvas: ${esc(String(e))}</div>`);
  }

  const hasFeedback =
    feedback.comments.length > 0 || feedback.rubric.some((r) => r.comment || r.points != null);
  if (!hasFeedback) {
    return panel.setBody(`<div class="csg-muted">No grader comments or rubric feedback on this assignment yet.</div>`);
  }

  panel.setBody(`<div class="csg-muted">Matching feedback to course material…</div>`);
  const res = await chrome.runtime.sendMessage({ type: "analyze", payload: { courseId, feedback } });
  if (!res?.ok) {
    return panel.setBody(`<div class="csg-err">Backend error: ${esc(res?.error || "no response")}<br>
      Is the backend running at localhost:8000?</div>`);
  }
  renderResults(panel, res.data);
}

async function getFeedback(courseId, assignmentId) {
  const url =
    `/api/v1/courses/${courseId}/assignments/${assignmentId}/submissions/self` +
    `?include[]=submission_comments&include[]=rubric_assessment&include[]=assignment`;
  const r = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  // Canvas sometimes prefixes JSON with "while(1);" as an anti-hijacking guard.
  const sub = JSON.parse((await r.text()).replace(/^while\(1\);/, ""));

  const rubric = sub.assignment?.rubric ?? [];
  return {
    assignment: sub.assignment?.name ?? "",
    description: stripHtml(sub.assignment?.description ?? "").slice(0, 2000),
    score: sub.score,
    pointsPossible: sub.assignment?.points_possible,
    comments: (sub.submission_comments ?? [])
      .filter((c) => c.author_id !== sub.user_id) // grader comments only, not the student's own
      .map((c) => c.comment)
      .filter(Boolean),
    rubric: rubric.map((r) => {
      const a = sub.rubric_assessment?.[r.id] ?? {};
      return { criterion: r.description, points: a.points ?? null, max: r.points, comment: a.comments || "" };
    }),
  };
}

function renderResults(panel, data) {
  const mistakes = data.mistakes ?? [];
  if (!mistakes.length) {
    return panel.setBody(`<div class="csg-muted">Nothing to review — no point deductions were found.</div>`);
  }
  panel.setBody(
    (data.summary ? `<p class="csg-summary">${esc(data.summary)}</p>` : "") +
      mistakes
        .map(
          (m) => `
      <div class="csg-item">
        <div class="csg-topic">${esc(m.topic)}</div>
        <div class="csg-why">${esc(m.why)}</div>
        ${
          m.resources?.length
            ? `<ul>${m.resources
                .map(
                  (r) =>
                    `<li><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>` +
                    (r.note ? `<div class="csg-note">${esc(r.note)}</div>` : "") +
                    `</li>`
                )
                .join("")}</ul>`
            : `<div class="csg-muted">No matching course material found — ask your TA.</div>`
        }
      </div>`
        )
        .join("")
  );
}

function createPanel() {
  const style = document.createElement("style");
  style.textContent = `
    #csg-panel{position:fixed;right:16px;bottom:16px;width:380px;max-height:70vh;display:flex;flex-direction:column;
      background:#fff;color:#222;border:1px solid #c7cdd1;border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.15);
      z-index:2147483647;font:14px/1.45 system-ui,sans-serif}
    #csg-panel header{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;
      background:#bb0000;color:#fff;border-radius:10px 10px 0 0;font-weight:600}
    #csg-panel header button{background:none;border:0;color:#fff;font-size:18px;cursor:pointer}
    #csg-body{padding:12px 14px;overflow:auto}
    .csg-btn{background:#bb0000;color:#fff;border:0;border-radius:6px;padding:8px 12px;cursor:pointer;font-weight:600}
    .csg-muted{color:#666}.csg-err{color:#b00}
    .csg-summary{margin:0 0 10px}
    .csg-item{border-top:1px solid #eee;padding:10px 0}
    .csg-topic{font-weight:600}.csg-why{margin:2px 0 6px}
    .csg-item ul{margin:0;padding-left:18px}.csg-note{color:#555;font-size:12px}
    #csg-panel.min #csg-body{display:none}`;
  document.head.appendChild(style);

  const el = document.createElement("div");
  el.id = "csg-panel";
  el.innerHTML = `<header><span>Study Guide</span><button title="Minimize">–</button></header><div id="csg-body"></div>`;
  el.querySelector("header button").onclick = () => el.classList.toggle("min");
  document.body.appendChild(el);

  return { el, setBody: (html) => (el.querySelector("#csg-body").innerHTML = html) };
}

function stripHtml(html) {
  // DOMParser documents are inert (no script/handler execution, no image loads).
  return new DOMParser().parseFromString(html, "text/html").body.textContent || "";
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
