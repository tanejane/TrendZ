/* Read-only, opt-in measured evidence explanation. No API keys in browser code. */
(() => {
  const form = document.getElementById('gemini-form');
  if (!form) return;
  const topic = document.getElementById('gemini-topic');
  const question = document.getElementById('gemini-question');
  const submit = document.getElementById('gemini-submit');
  const status = document.getElementById('gemini-status');
  const answer = document.getElementById('gemini-answer');
  const source = document.getElementById('gemini-source');

  fetch('/api/trends', { credentials: 'same-origin' })
    .then(r => { if (!r.ok) throw Error('Topics unavailable'); return r.json(); })
    .then(data => {
      topic.replaceChildren();
      const observed = (data.trends || []).filter(t => t.data_mode === 'real');
      for (const trend of observed) {
        const opt = document.createElement('option');
        opt.value = trend.id;
        opt.textContent = trend.name || trend.query || trend.id;
        topic.appendChild(opt);
      }
      if (!observed.length) {
        topic.add(new Option('No measured evidence available', ''));
        submit.disabled = true;
      }
    })
    .catch(() => { status.textContent = 'Could not load measured topics.'; submit.disabled = true; });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    submit.disabled = true;
    status.textContent = 'Requesting an explanation…';
    answer.textContent = '';
    source.hidden = true;
    try {
      const response = await fetch('/api/assistant/explain', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ topic_id: topic.value, question: question.value })
      });
      const data = await response.json();
      if (!response.ok) throw Error(data.message || 'Explanation unavailable');
      answer.textContent = data.answer; // textContent avoids XSS from generated output.
      status.textContent = data.disclaimer;
      source.href = data.evidence_url;
      source.hidden = false;
      source.textContent = 'Inspect the underlying topic evidence';
    } catch (error) { status.textContent = error.message; }
    finally { submit.disabled = false; }
  });
})();
