(() => {
    const form = document.querySelector('#scenario-form');
    if (!form) return;
    const status = document.querySelector('#scenario-status');
    const error = document.querySelector('#scenario-error');
    let context, lastResult, generation = 0;
    function el(tag, text, parent) { const n = document.createElement(tag); if (text != null) n.textContent = text; parent?.append(n); return n; }
    const label = value => String(value ?? 'Unavailable').replaceAll('_', ' ');
    const node = id => document.getElementById(id);
    function list(values, parent) { values.forEach(v => el('li', v, parent)); }
    function clear() {
        generation++; lastResult = null; node('scenario-outcomes').replaceChildren();
        node('scenario-sensitivity').replaceChildren(); node('scenario-break-even').replaceChildren(); node('result-details').hidden = true;
    }
    function showError(e) { error.querySelector('p').textContent = e.message; error.hidden = false; }
    async function read(url, options) {
        const r = await fetch(url, options); const d = await r.json();
        if (!r.ok || d.status !== 'success') throw new Error(`${d.code || 'request_error'}: ${d.message || 'Request failed'}`);
        return d;
    }
    function dl(values, parent) {
        const d = el('dl', null, parent);
        Object.entries(values).forEach(([key, value]) => { const row = el('div', null, d); el('dt', key, row); el('dd', value, row); });
    }
    function display(v) {
        if (v.state !== 'available') return `Unavailable: ${v.reason}`;
        const n = v.display_value ?? v.value;
        return v.unit === 'MYR' ? `RM ${n}` : v.unit === 'percent' ? `${n}%` : `${n} ${v.unit}`;
    }
    function percentage(value) {
        if (!value) return null;
        const match = /^(\d+)(?:\.(\d+))?$/.exec(value.startsWith('.') ? '0' + value : value);
        if (!match) throw new Error('Enter percentages as nonnegative decimal values');
        const whole = match[1].padStart(3, '0');
        return whole.slice(0, -2) + '.' + whole.slice(-2) + (match[2] || '');
    }
    function link(title, url, parent) {
        try { const u = new URL(url); if (u.protocol !== 'https:' || u.username || u.password) throw new Error();
            const a = el('a', title, parent); a.href = u.href; a.target = '_blank'; a.rel = 'noopener noreferrer';
        } catch (_) { el('span', title, parent); }
    }
    async function bootstrap() {
        clear(); context = null; form.hidden = true; error.hidden = true;
        node('manual-ack').hidden = true; form.manual_accepted.checked = false; form.manual_reason.value = '';
        status.textContent = 'Loading pinned evidence...';
        try {
            context = await read(`/api/campaign-scenarios/context${location.search}`);
            const e = context.evidence, c = e.creator_candidate, p = e.product_fit;
            document.dispatchEvent(new CustomEvent('trendz:scenario-context', {detail:context}));
            node('scenario-evidence').replaceChildren(); node('evidence-links').replaceChildren();
            const values = {'Topic / query / market': `${e.trend.topic_id} / ${e.trend.query} / ${e.trend.market}`,
                'Product Fit': `${p.product_name}: ${label(p.fit_state)}${p.fit_state === 'supporting_fit' ? ' (indirect compatibility)' : ''}`,
                'Creator candidate': `${c.creator_name}: ${label(c.candidate_state)}`,
                'Reviewed specialization': c.specializations.join(', ') || 'None reviewed', 'Topic affinity': label(c.topic_affinity),
                'Audience evidence': c.market_evidence.audience_geography?.state || 'unknown',
                'Engagement': c.engagement_available ? 'Descriptive retrieval-time sample only' : 'Unavailable',
                'Review basis': `Profile: ${c.review_basis.profile}; affinity: ${c.review_basis.affinity}`};
            for (const [key, d] of Object.entries(e.trend.dimensions)) values[label(key === 'data_confidence' ? 'evidence_quality' : key)] = `${d.state}; ${d.observation_window?.start || 'no window'} to ${d.observation_window?.end || 'no window'}`;
            dl(values, node('scenario-evidence'));
            node('evidence-provenance').textContent = JSON.stringify({context_ref: context.context_ref, evidence: e}, null, 2);
            const videos = el('ul', null, node('evidence-links'));
            c.evidence.affinity.forEach(v => link(`${v.title || v.video_id} / ${v.published_at || 'date unavailable'}`, v.url, el('li', null, videos)));
            node('scenario-warnings').replaceChildren(); list(context.warnings, node('scenario-warnings'));
            if (!context.scenario_eligible) { status.textContent = 'Blocked: Product Fit or creator evidence is unavailable/ineligible.'; return; }
            form.hidden = false; node('manual-ack').hidden = c.candidate_state !== 'manual_review_only';
            status.textContent = 'Evidence pinned. Enter explicit campaign assumptions.';
        } catch (e) { showError(e); status.textContent = 'Scenario context unavailable.'; }
    }
    function assumptions() {
        const v = name => form.elements.namedItem(name).value || null;
        const basis = v('conversion_basis');
        return {objective: v('objective'), format: v('format'), channel: v('channel'), currency: v('currency'),
            campaign_window: {start_date: v('start_date'), end_date_exclusive: v('end_date_exclusive')},
            costs: Object.fromEntries(['creator_fee', 'media_spend', 'production_cost', 'other_cost'].map(k => [k, v(k)])),
            budget_ceiling: v('budget_ceiling'), conversion_basis: basis,
            population: {value: v('population') == null ? null : Number(v('population')), unit: basis === 'assumed_reach' ? 'unique_reached_people' : basis === 'target_population' ? 'target_people' : null,
                basis: v('population_basis'), source_ref: v('population_source')},
            conversion_rates: Object.fromEntries(['low', 'base', 'high'].map(k => [k, percentage(v(k + '_rate'))])),
            aov: v('aov'), gross_margin_rate: percentage(v('gross_margin')), source_notes: v('source_notes'),
            manual_candidate_acknowledgement: {accepted: form.manual_accepted.checked, reason: v('manual_reason')}};
    }
    function render(d) {
        lastResult = d; el('p', d.scenario_explanation, node('scenario-outcomes'));
        const base = d.calculated_outcomes.base;
        dl({'Total cost': display(d.calculated_outcomes.total_cost), 'Budget headroom': display(d.calculated_outcomes.budget_headroom),
            'Modeled conversions': display(base.modeled_conversions), 'Modeled revenue': display(base.modeled_revenue),
            'Modeled gross profit': display(base.modeled_gross_profit), 'Modeled net profit': display(base.modeled_net_profit),
            'Modeled ROI': display(base.modeled_roi_percent)}, node('scenario-outcomes'));
        const wrap = el('div', null, node('scenario-sensitivity')); wrap.className = 'table-scroll';
        const table = el('table', null, wrap); table.setAttribute('aria-label', 'Explicit conversion sensitivity');
        const head = el('tr', null, el('thead', null, table));
        ['Scenario', 'Assumed rate (fraction)', 'Modeled orders', 'Modeled revenue', 'Modeled net profit', 'Modeled ROI'].forEach(t => { const h = el('th', t, head); h.scope = 'col'; });
        const body = el('tbody', null, table);
        d.sensitivity.forEach(r => { const row = el('tr', null, body); [r.scenario, r.assumed_conversion_rate ?? 'Unavailable', display(r.modeled_conversions), display(r.modeled_revenue), display(r.modeled_net_profit), display(r.modeled_roi_percent)].forEach(t => el('td', t, row)); });
        dl({'Break-even revenue': display(d.break_even.revenue), 'Break-even conversions': display(d.break_even.conversions),
            'Minimum whole orders': display(d.break_even.minimum_whole_orders),
            'Break-even conversion rate': display(d.break_even.conversion_rate_percent)}, node('scenario-break-even'));
        el('p', label(d.break_even.feasibility), node('scenario-break-even'));
        node('scenario-warnings').replaceChildren(); list(d.warnings, node('scenario-warnings'));
        const scope = el('details', null, node('scenario-outcomes')); el('summary', 'Scope and limitations', scope);
        const limits = el('ul', null, scope); list(d.limitations, limits);
        node('scenario-json').textContent = JSON.stringify(d, null, 2); node('result-details').hidden = false;
        status.textContent = `${label(d.scenario_state)}: assumption-based calculation, not campaign performance.`;
    }
    form.addEventListener('input', () => { clear(); error.hidden = true; status.textContent = 'Assumptions changed. Recalculate to see outcomes.'; });
    form.addEventListener('change', () => { clear(); error.hidden = true; status.textContent = 'Assumptions changed. Recalculate to see outcomes.'; });
    form.addEventListener('submit', async event => {
        event.preventDefault(); clear(); error.hidden = true; const current = generation;
        const button = form.querySelector('[type=submit]'); button.disabled = true; status.textContent = 'Calculating scenario...';
        try {
            const data = await read('/api/campaign-scenarios/evaluate', {method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({schema_version: 'campaign-scenario-v1', calculation_version: context.calculation_version,
                    context_ref: context.context_ref, assumptions: assumptions()})});
            if (current === generation) render(data);
        } catch (e) { if (current === generation) { showError(e); status.textContent = 'Calculation unavailable. No previous result retained.'; } }
        finally { button.disabled = false; }
    });
    node('refresh-context').addEventListener('click', bootstrap);
    node('download-scenario').addEventListener('click', () => { if (!lastResult) return;
        const url = URL.createObjectURL(new Blob([JSON.stringify(lastResult, null, 2)], {type: 'application/json'}));
        const a = document.createElement('a'); a.href = url; a.download = 'trendz-campaign-scenario.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    bootstrap();
})();
