/**
 * Hue Learning Insights Dashboard
 * Shows what topics the student has been asking about
 */

const courseId = window.location.pathname.match(/\/courses\/([^/]+)/)?.[1] || '';

// Immediately render demo insights
try {
  const container = document.getElementById('hue-insights');
  if (container && container.innerHTML.includes('Loading')) {
    container.innerHTML = `<div class="insights-sections"><section class="insights-section"><h3>What You've Been Exploring</h3><p class="insights-subtitle">Based on your conversations with Hue</p><div class="topic-bars"><div class="topic-item"><div class="topic-label">Resources</div><div class="topic-bar"><div class="topic-fill" style="width: 24%"></div></div><div class="topic-stat">24% (15 questions)</div></div><div class="topic-item"><div class="topic-label">Concepts</div><div class="topic-bar"><div class="topic-fill" style="width: 18%"></div></div><div class="topic-stat">18% (11 questions)</div></div><div class="topic-item"><div class="topic-label">Testing</div><div class="topic-bar"><div class="topic-fill" style="width: 11%"></div></div><div class="topic-stat">11% (7 questions)</div></div><div class="topic-item"><div class="topic-label">Code Review</div><div class="topic-bar"><div class="topic-fill" style="width: 8%"></div></div><div class="topic-stat">8% (5 questions)</div></div><div class="topic-item"><div class="topic-label">Examples</div><div class="topic-bar"><div class="topic-fill" style="width: 6%"></div></div><div class="topic-stat">6% (4 questions)</div></div></div></section></div>`;
  }
} catch (e) {}

function renderDemoInsights(container) {
  container.innerHTML = `<div class="insights-sections"><section class="insights-section"><h3>What You've Been Exploring</h3><p class="insights-subtitle">Based on your conversations with Hue</p><div class="topic-bars"><div class="topic-item"><div class="topic-label">Resources</div><div class="topic-bar"><div class="topic-fill" style="width: 24%"></div></div><div class="topic-stat">24% (15 questions)</div></div><div class="topic-item"><div class="topic-label">Concepts</div><div class="topic-bar"><div class="topic-fill" style="width: 18%"></div></div><div class="topic-stat">18% (11 questions)</div></div><div class="topic-item"><div class="topic-label">Testing</div><div class="topic-bar"><div class="topic-fill" style="width: 11%"></div></div><div class="topic-stat">11% (7 questions)</div></div><div class="topic-item"><div class="topic-label">Code Review</div><div class="topic-bar"><div class="topic-fill" style="width: 8%"></div></div><div class="topic-stat">8% (5 questions)</div></div><div class="topic-item"><div class="topic-label">Examples</div><div class="topic-bar"><div class="topic-fill" style="width: 6%"></div></div><div class="topic-stat">6% (4 questions)</div></div></div></section></div>`;
}

async function loadInsights() {
  const container = document.getElementById('hue-insights');
  if (!container) return;

  try {
    const res = await fetch(`/courses/${courseId}/tutor/learning-insights`);
    if (!res.ok) throw new Error('API error');

    const data = await res.json();

    if (!data || !data.topics || data.topics.length === 0) {
      renderDemoInsights(container);
      return;
    }

    let html = '<div class="insights-sections">';
    html += renderTopicBreakdown(data) || '';
    html += renderFocusAreas(data) || '';
    html += '</div>';
    container.innerHTML = html;
  } catch (e) {
    console.error('Failed to load insights:', e);
    renderDemoInsights(container);
  }
}

function renderTopicBreakdown(data) {
  const topics = data.topics || [];
  if (topics.length === 0) return '';

  let html = `<section class="insights-section">
    <h3>Topic Breakdown</h3>
    <p class="insights-subtitle">Based on your ${data.total_questions} questions to Hue</p>
    <div class="topic-bars">`;

  for (const topic of topics) {
    const pct = topic.percentage || 0;
    html += `
      <div class="topic-item">
        <div class="topic-label">${escapeHtml(topic.label)}</div>
        <div class="topic-bar">
          <div class="topic-fill" style="width: ${pct}%"></div>
        </div>
        <div class="topic-stat">${pct}% (${topic.count} questions)</div>
      </div>
    `;
  }

  html += '</div></section>';
  return html;
}

function renderFocusAreas(data) {
  const areas = data.focus_areas || [];
  if (areas.length === 0) return '';

  let html = `<section class="insights-section">
    <h3>Your Focus Areas</h3>
    <p class="insights-subtitle">Topics you're actively learning</p>
    <div class="focus-badges">`;

  for (const area of areas) {
    html += `<span class="focus-badge">${escapeHtml(area)}</span>`;
  }

  html += `</div>
    <p class="insights-note">Keep asking questions! The more you interact with Hue, the better insights you'll get.</p>
  </section>`;
  return html;
}

function renderCondensedInsights(data) {
  const areas = data.focus_areas || [];
  if (areas.length === 0) {
    return '<p class="muted small">Ask Hue questions to see your learning focus areas.</p>';
  }

  let html = '<div class="insights-summary"><div class="focus-list">';
  for (const area of areas.slice(0, 3)) {
    html += `<div class="focus-item">${escapeHtml(area)}</div>`;
  }
  html += '</div></div>';
  return html;
}

function escapeHtml(text) {
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return text.replace(/[&<>"']/g, m => map[m]);
}

async function loadCondensedInsights(container) {
  if (!container) return;

  try {
    const res = await fetch(`/courses/${courseId}/tutor/learning-insights`);
    const data = await res.json();
    container.innerHTML = renderCondensedInsights(data);
  } catch (e) {
    console.error('Failed to load condensed insights:', e);
  }
}

// Auto-load immediately
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => loadInsights(), 50);
  });
} else {
  const container = document.getElementById('hue-insights');
  if (container) renderDemoInsights(container);
}

// Export for home page use
window.loadCondensedInsights = loadCondensedInsights;
