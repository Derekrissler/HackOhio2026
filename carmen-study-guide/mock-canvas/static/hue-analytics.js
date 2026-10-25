/**
 * Hue Analytics Dashboard
 * Renders learning progress data from the analytics pipeline
 */

// Extract course ID from the page URL
const courseId = window.location.pathname.match(/\/courses\/([^/]+)/)?.[1] || '';

function renderDemoAnalytics(container) {
  const html = `
    <div class="analytics-sections">
      <section class="analytics-section outcome-grid">
        <h3>Your Learning Progress</h3>
        <div style="display: grid; gap: 12px;">
          <div class="outcome-card strong">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <strong>Code Quality & Style</strong>
              <span style="font-size: 12px; color: #999;">89%</span>
            </div>
            <div style="height: 6px; background: #e0e0e0; border-radius: 3px; overflow: hidden;">
              <div style="height: 100%; width: 89%; background: linear-gradient(90deg, #2f9e44, #0374b5);"></div>
            </div>
          </div>
          <div class="outcome-card strong">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <strong>Testing & Debugging</strong>
              <span style="font-size: 12px; color: #999;">78%</span>
            </div>
            <div style="height: 6px; background: #e0e0e0; border-radius: 3px; overflow: hidden;">
              <div style="height: 100%; width: 78%; background: linear-gradient(90deg, #2f9e44, #0374b5);"></div>
            </div>
          </div>
          <div class="outcome-card developing">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <strong>Design Patterns</strong>
              <span style="font-size: 12px; color: #999;">62%</span>
            </div>
            <div style="height: 6px; background: #e0e0e0; border-radius: 3px; overflow: hidden;">
              <div style="height: 100%; width: 62%; background: linear-gradient(90deg, #f5a300, #8f3e97);"></div>
            </div>
          </div>
        </div>
      </section>

      <section class="analytics-section">
        <h3>Focus Areas</h3>
        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
          <span class="outcome-badge strong">Code Structure</span>
          <span class="outcome-badge developing">Testing</span>
          <span class="outcome-badge developing">Best Practices</span>
          <span class="outcome-badge focus">Documentation</span>
        </div>
      </section>

      <section class="analytics-section">
        <p class="analytics-note" style="color: #666; font-size: 14px;">Demo dashboard. Complete more assignments to see personalized analytics.</p>
      </section>
    </div>
  `;
  container.innerHTML = html;
}

async function loadAnalytics() {
  const container = document.getElementById('hue-analytics');
  if (!container) return;

  try {
    const res = await fetch(`/courses/${courseId}/tutor/analytics`);
    const data = await res.json();

    if (data.status === 'unavailable' || data.status === 'no_results') {
      return renderDemoAnalytics(container);
    }

    if (data.status !== 'ready') {
      return renderDemoAnalytics(container);
    }

    // Group performance data by scope
    const classOutcomes = data.performance.filter(p => p.scope === 'class_outcome' && !p.suppressed && !p.insufficient_evidence);
    const studentOutcomes = data.performance.filter(p => p.scope === 'student_outcome' && !p.suppressed && !p.insufficient_evidence);
    const assessmentQuestions = data.performance.filter(p => p.scope === 'assessment_question' && !p.suppressed && !p.insufficient_evidence);

    let html = '<div class="analytics-sections">';

    // Your Strengths & Weaknesses
    if (studentOutcomes.length > 0) {
      html += renderStudentOutcomes(studentOutcomes);
    }

    // Class Performance Trends
    if (classOutcomes.length > 0) {
      html += renderClassOutcomes(classOutcomes);
    }

    // Question-Specific Insights
    if (assessmentQuestions.length > 0 && assessmentQuestions.length <= 20) {
      html += renderAssessmentQuestions(assessmentQuestions);
    }

    // Error Patterns
    if (data.clusters.length > 0) {
      html += renderErrorPatterns(data.clusters);
    }

    // Interpretation note
    html += `<section class="analytics-section">
      <p class="analytics-note">${escapeHtml(data.interpretation)}</p>
      ${data.computed_at ? `<p class="analytics-time">Updated ${new Date(data.computed_at).toLocaleString()}</p>` : ''}
    </section>`;

    html += '</div>';
    container.innerHTML = html;
  } catch (e) {
    console.error('Failed to load analytics:', e);
    container.innerHTML = `
      <div class="analytics-empty">
        <p class="muted">Error loading analytics. Please refresh the page.</p>
      </div>
    `;
  }
}

function renderStudentOutcomes(outcomes) {
  const sorted = outcomes.sort((a, b) => {
    const aScore = a.observed_score_ratio ?? 0;
    const bScore = b.observed_score_ratio ?? 0;
    return bScore - aScore; // Highest first
  });

  let html = `<section class="analytics-section">
    <h3>Your Learning Progress</h3>
    <div class="outcome-grid">`;

  for (const outcome of sorted) {
    const score = outcome.observed_score_ratio ?? 0;
    const pct = Math.round(score * 100);
    const status = pct >= 80 ? 'strong' : pct >= 60 ? 'developing' : 'focus';

    html += `
      <div class="outcome-card outcome-${status}">
        <div class="outcome-label">${escapeHtml(outcome.label)}</div>
        <div class="outcome-bar">
          <div class="outcome-fill" style="width: ${pct}%"></div>
        </div>
        <div class="outcome-stat">${pct}% demonstrated</div>
        ${outcome.score_observations ? `<div class="outcome-count">${outcome.score_observations} assessments</div>` : ''}
      </div>
    `;
  }

  html += '</div></section>';
  return html;
}

function renderClassOutcomes(outcomes) {
  const sorted = outcomes.sort((a, b) => {
    const aScore = a.mean_student_ratio ?? 0;
    const bScore = b.mean_student_ratio ?? 0;
    return bScore - aScore;
  });

  let html = `<section class="analytics-section">
    <h3>Class Trends</h3>
    <div class="trend-table">
      <div class="trend-header">
        <div class="trend-label">Learning Goal</div>
        <div class="trend-value">Class Avg</div>
      </div>`;

  for (const outcome of sorted.slice(0, 10)) {
    const pct = outcome.mean_student_ratio ? Math.round(outcome.mean_student_ratio * 100) : 0;
    html += `
      <div class="trend-row">
        <div class="trend-label">${escapeHtml(outcome.label)}</div>
        <div class="trend-bar">
          <div class="trend-fill" style="width: ${pct}%"></div>
          <div class="trend-pct">${pct}%</div>
        </div>
      </div>
    `;
  }

  html += '</div></section>';
  return html;
}

function renderAssessmentQuestions(questions) {
  const sorted = questions.sort((a, b) => {
    const aScore = a.pooled_score_ratio ?? 0;
    const bScore = b.pooled_score_ratio ?? 0;
    return aScore - bScore; // Lowest (most difficult) first
  });

  let html = `<section class="analytics-section">
    <h3>Question Performance</h3>
    <div class="questions-list">`;

  for (const q of sorted) {
    const pct = q.pooled_score_ratio ? Math.round(q.pooled_score_ratio * 100) : 0;
    const difficulty = pct < 40 ? 'hard' : pct < 70 ? 'moderate' : 'easy';

    html += `
      <div class="question-item question-${difficulty}">
        <div class="question-label">${escapeHtml(q.label)}</div>
        <div class="question-stat">${pct}% correct ${q.assessed_students ? `(${q.assessed_students} students)` : ''}</div>
      </div>
    `;
  }

  html += '</div></section>';
  return html;
}

function renderErrorPatterns(clusters) {
  if (clusters.length === 0) return '';

  let html = `<section class="analytics-section">
    <h3>Common Misconceptions</h3>
    <div class="error-clusters">`;

  for (const cluster of clusters.slice(0, 5)) {
    html += `
      <div class="error-item">
        <div class="error-header">
          <div class="error-code">${escapeHtml(cluster.error_code)}</div>
          <div class="error-count">${cluster.unique_students} students</div>
        </div>
        <div class="error-assessment">${escapeHtml(cluster.assessment_origin)}</div>
        ${cluster.representative_text ? `<div class="error-text"><em>"${escapeHtml(cluster.representative_text)}"</em></div>` : ''}
        <div class="error-help">${escapeHtml(cluster.assistance)}</div>
      </div>
    `;
  }

  html += '</div></section>';
  return html;
}

function renderCondensedAnalytics(data) {
  // Used on home page: just show top 3 outcomes
  const outcomes = data.performance
    .filter(p => p.scope === 'student_outcome' && !p.suppressed && !p.insufficient_evidence)
    .sort((a, b) => (b.observed_score_ratio ?? 0) - (a.observed_score_ratio ?? 0))
    .slice(0, 3);

  if (outcomes.length === 0) {
    return '<p class="muted small">Complete assessments to see your progress.</p>';
  }

  let html = '<div class="analytics-summary">';
  for (const outcome of outcomes) {
    const pct = Math.round((outcome.observed_score_ratio ?? 0) * 100);
    const status = pct >= 80 ? 'strong' : pct >= 60 ? 'developing' : 'focus';
    html += `
      <div class="summary-item summary-${status}">
        <div class="summary-label">${escapeHtml(outcome.label)}</div>
        <div class="summary-bar"><div class="summary-fill" style="width: ${pct}%"></div></div>
        <div class="summary-pct">${pct}%</div>
      </div>
    `;
  }
  html += '</div>';
  return html;
}

async function loadCondensedAnalytics(container) {
  if (!container) return;

  try {
    const res = await fetch(`/courses/${courseId}/tutor/analytics`);
    const data = await res.json();

    if (data.status !== 'ready') {
      container.innerHTML = '<p class="muted small">Analytics coming soon.</p>';
      return;
    }

    container.innerHTML = renderCondensedAnalytics(data);
  } catch (e) {
    console.error('Failed to load condensed analytics:', e);
  }
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

// Auto-load on DOMContentLoaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', loadAnalytics);
} else {
  loadAnalytics();
}

// Export for home page use
window.loadCondensedAnalytics = loadCondensedAnalytics;
