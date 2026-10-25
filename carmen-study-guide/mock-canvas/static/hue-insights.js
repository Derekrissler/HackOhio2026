/**
 * Hue Learning Insights Dashboard
 * Shows what topics the student has been asking about
 */

const courseId = window.location.pathname.match(/\/courses\/([^/]+)/)?.[1] || '';

async function loadInsights() {
  const container = document.getElementById('hue-insights');
  if (!container) return;

  try {
    const res = await fetch(`/courses/${courseId}/tutor/learning-insights`);
    const data = await res.json();

    if (!data.topics || data.topics.length === 0) {
      container.innerHTML = `
        <div class="insights-empty">
          <p class="muted">Start a conversation with Hue to see what you've been learning about!</p>
        </div>
      `;
      return;
    }

    let html = '<div class="insights-sections">';
    html += renderTopicBreakdown(data);
    html += renderFocusAreas(data);
    html += '</div>';
    container.innerHTML = html;
  } catch (e) {
    console.error('Failed to load insights:', e);
    container.innerHTML = `
      <div class="insights-empty">
        <p class="muted">Error loading insights. Try refreshing the page.</p>
      </div>
    `;
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

// Auto-load on DOMContentLoaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', loadInsights);
} else {
  loadInsights();
}

// Export for home page use
window.loadCondensedInsights = loadCondensedInsights;
