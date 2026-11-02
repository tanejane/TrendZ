/* Frozen context pins are sent on every evaluation. Never order by counters. */
(() => {
    const root = document.querySelector('[data-creator-topic]');
    if (!root) return;
    const form = root.querySelector('form');
    const status = root.querySelector('[role="status"]');
    const error = root.querySelector('[role="alert"]');
    const results = root.querySelector('.tz-creator-results');
    const order = root.querySelector('.tz-creator-order');
    let context, generation = 0, controller;
    const text = value => Array.isArray(value) ? value.join(', ') || 'None reviewed' : String(value ?? 'Unavailable');
    const label = value => text(value).replaceAll('_', ' ');
    function node(tag, value, parent, className) {
        const el = document.createElement(tag);
        if (value != null) el.textContent = text(value);
        if (className) el.className = className;
        if (parent) parent.append(el);
        return el;
    }
    function link(title, url, parent) {
        try {
            const parsed = new URL(url);
            if (parsed.protocol !== 'https:' || parsed.username || parsed.password) throw new Error();
            const a = node('a', title, parent);
            a.href = parsed.href; a.target = '_blank'; a.rel = 'noopener noreferrer';
        } catch (_) { node('span', title, parent); }
    }
    async function read(url, signal) {
        const response = await fetch(url, {signal});
        const data = await response.json();
        if (!response.ok || data.status !== 'success') throw new Error(data.message || 'Evidence could not be loaded');
        return data;
    }
    function clear() {
        generation++; controller?.abort(); results.replaceChildren(); order.hidden = true;
        error.hidden = true; results.setAttribute('aria-busy', 'false');
        form.querySelector('button').disabled = false;
    }
    function fail(e) {
        error.querySelector('p').textContent = e.message;
        error.hidden = false; status.textContent = 'No candidate results displayed.';
    }
    function card(c) {
        const item = node('article', null, results, 'tz-creator-card');
        item.dataset.state = c.candidate_state;
        const header = node('header', null, item);
        const identity = node('div', null, header, 'creator-identity');
        const avatar = node('span', c.creator_name.split(/\s+/).slice(0,2).map(v => v[0]).join(''), identity, 'creator-avatar');
        avatar.setAttribute('aria-hidden','true');
        const h = node('h3', null, identity); link(c.creator_name, c.channel_url, h);
        node('span', label(c.candidate_state), header, 'tz-creator-state');
        node('p', c.reasons.at(-1), item);
        const dl = node('dl', null, item);
        const audience = c.market_evidence.audience_geography || {};
        const fields = {
            'Specialization': c.specializations,
            'Topic affinity': label(c.topic_affinity), 'Profile support': label(c.profile_support),
            'Product specialization': `${text(c.product_required_specialization)} / matched: ${text(c.matched_specialization)}`,
            'Evidence sufficiency': `Profile: ${c.evidence_sufficiency.profile}; topic: ${c.evidence_sufficiency.affinity}`,
            'Supporting references': `${new Set([...c.evidence_ids.profile, ...c.evidence_ids.affinity]).size} distinct videos`,
            'MY audience evidence': `${audience.state || 'unknown'}; ${text(audience.value)}`,
            'Engagement evidence': c.engagement_available ? 'Available, retrieval-time descriptions only' : 'Unavailable'
        };
        for (const [key, value] of Object.entries(fields)) {
            const row = node('div', null, dl); node('dt', key, row); node('dd', value, row);
        }
        const warnings = node('ul', null, item);
        [...c.warnings, c.explicitness_warning, 'No product use or endorsement inferred.'].forEach(v => node('li', v, warnings));
        if (['strong_evidence_candidate', 'qualified_candidate', 'manual_review_only'].includes(c.candidate_state)) {
            const params = new URLSearchParams({...context.pins, topic_id: context.topic_id,
                query_id: context.query_id, market: context.market, product_id: form.product_id.value,
                creator_id: c.creator_id, calculation_version: 'campaign-economics-v1',
                required_market_evidence: form.required_market_evidence.value,
                engagement_requirement: form.engagement_requirement.value});
            const action = node('a', 'Build Campaign Scenario', item, 'tz-campaign-action');
            action.href = '/campaign-scenario?' + params.toString();
        }
        const details = node('details', null, item);
        node('summary', 'Evidence and provenance', details);
        for (const scope of ['profile', 'affinity']) {
            node('h4', `${label(scope)} supporting videos`, details);
            const list = node('ul', null, details);
            for (const video of c.evidence[scope]) {
                const li = node('li', null, list);
                link(video.title || `Video ${video.video_id} (title unavailable)`, video.url, li);
                node('p', `Published: ${text(video.published_at)}; retrieved: ${text(video.retrieved_at)}`, li);
                node('p', `Run: ${text(video.source_ref?.run_id)}; ID: ${video.video_id}`, li);
            }
        }
        node('h4', 'Product Fit context', details);
        node('p', `${c.product_fit_provenance.product_name} / ${label(c.product_fit_provenance.fit_state)}`, details);
        const sources = node('ul', null, details);
        const urls = new Set(c.product_fit_provenance.supporting_evidence.map(v => v.source?.url).filter(Boolean));
        for (const url of urls) link('Product evidence source', url, node('li', null, sources));
        node('pre', JSON.stringify({reviewed_domain:c.reviewed_domain,observation_cutoff:c.observation_cutoff,review_basis: c.review_basis, review: c.review_provenance,
            product_fit: c.product_fit_provenance, engagement: c.engagement_evidence,
            market: c.market_evidence, policy_version: c.policy_version}, null, 2), details);
        const limits = node('ul', null, details);
        c.limitations.forEach(v => node('li', v, limits));
    }
    async function bootstrap() {
        clear(); status.textContent = 'Loading frozen Product Fit context...';
        try {
            context = await read(`/api/creator-candidates/context/${encodeURIComponent(root.dataset.creatorTopic)}`);
            form.product_id.replaceChildren(new Option('Select a positive product', ''));
            for (const p of context.products) form.product_id.add(new Option(`${p.product_name} / ${label(p.fit_state)} / ${p.category}`, p.product_id));
            form.hidden = !context.products.length;
            root.querySelector('.tz-creator-context').textContent = `${context.canonical_topic} / ${context.query_id} / ${context.market} | ${context.pins.product_fit_version} | ${context.pins.catalogue_version} | ${context.pins.creator_policy_version}`;
            status.textContent = context.products.length ? 'Select a positive Product Fit context.' : 'No positive products in this frozen context.';
            root.dispatchEvent(new CustomEvent('trendz:products-ready', {bubbles:true,detail:context}));
        } catch (e) { fail(e); }
    }
    async function load() {
        clear();
        if (!form.product_id.value) { status.textContent = 'Select a positive Product Fit context.'; return; }
        const current = generation;
        controller = new AbortController();
        const params = new URLSearchParams({...context.pins, topic_id: context.topic_id,
            query_id: context.query_id, market: context.market, ...Object.fromEntries(new FormData(form))});
        results.setAttribute('aria-busy', 'true'); form.querySelector('button').disabled = true;
        status.textContent = 'Loading evidence-gated candidates...';
        try {
            const data = await read(`/api/creator-candidates?${params}`, controller.signal);
            if (current !== generation) return;
            data.candidates.forEach(card); order.hidden = false;
            const states = ['strong_evidence_candidate', 'qualified_candidate', 'manual_review_only', 'unavailable', 'ineligible'];
            status.textContent = data.candidates.length ? states.map(k => `${label(k)}: ${data.counts[k]}`).join(' | ') : 'No reviewed creator-topic pairs in this fixed set.';
            root.dispatchEvent(new CustomEvent('trendz:candidates-ready', {bubbles:true}));
        } catch (e) { if (current === generation && e.name !== 'AbortError') fail(e); }
        finally { if (current === generation) { results.setAttribute('aria-busy', 'false'); form.querySelector('button').disabled = false; } }
    }
    form.addEventListener('submit', e => { e.preventDefault(); load(); });
    form.addEventListener('change', () => { clear(); status.textContent = 'Context changed. View candidates to load the selected context.'; });
    error.querySelector('button').addEventListener('click', () => context ? load() : bootstrap());
    bootstrap();
})();
