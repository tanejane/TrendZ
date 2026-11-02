(function (root) {
    'use strict';
    const dimensions = [
        ['demand_momentum', 'Demand Momentum'], ['signal_persistence', 'Signal Persistence'],
        ['content_saturation', 'Content Saturation'], ['creator_diversity', 'Creator Diversity'],
        ['engagement_velocity', 'Engagement Velocity'], ['data_confidence', 'Evidence Quality']
    ];
    const labels = { channel_hhi: 'Channel concentration (HHI)', query_id: 'Query ID',
        audit_pending: 'Pending audit candidates', google_zero_days: 'Zero-valued search days' };
    const states = new Set(['available', 'provisional', 'unavailable']);
    function humanize(value) {
        return labels[value] || String(value).replace(/_/g, ' ').replace(/^./, letter => letter.toUpperCase()).replace(/^Youtube /, 'YouTube ');
    }
    function formatValue(value, unit) {
        if (value === null || value === undefined) return 'Unavailable';
        if (typeof value === 'number') {
            if (!Number.isFinite(value)) return 'Unavailable';
            const number = new Intl.NumberFormat('en', { maximumFractionDigits: 6 }).format(value);
            return number + (unit === 'percent' ? '%' : unit === 'percentage_points' ? ' pp' : unit ? ' ' + unit.replace(/_/g, ' ') : '');
        }
        if (Array.isArray(value)) return value.length ? value.map(item => formatValue(item)).join(', ') : 'None reported';
        if (typeof value === 'string' && ['available', 'unavailable', 'provisional', 'deferred_or_pending',
            'reviewed_sample', 'selected_surviving_runs_only', 'immutable_runs', 'observations_only'].includes(value)) return humanize(value);
        return typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value);
    }
    function componentRows(value, path = []) {
        if (value && typeof value === 'object' && !Array.isArray(value)) {
            if ('state' in value && ('value' in value || 'reason' in value)) {
                return [{ label: path.map(humanize).join(' / '),
                    value: value.state === 'unavailable' ? 'Unavailable' : formatValue(value.value, value.unit),
                    reason: value.reason || '', state: value.state }];
            }
            return Object.entries(value).flatMap(([key, child]) => componentRows(child, [...path, key]));
        }
        return [{ label: path.map(humanize).join(' / '), value: formatValue(value), reason: '' }];
    }
    function dateLabel(value) {
        if (!value) return null;
        const parsed = new Date(value + 'T00:00:00Z');
        return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat('en-GB', {
            day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'
        }).format(parsed);
    }
    function windowLabel(window) {
        const start = dateLabel(window?.start), end = dateLabel(window?.end);
        return start && end ? start + ' to ' + end : 'No observation window';
    }
    function node(document, tag, className, text) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = text;
        return element;
    }
    function renderDimension(document, key, title, dimension) {
        const section = node(document, 'section', 'tz-dimension');
        section.dataset.dimension = key;
        const header = node(document, 'div', 'tz-dimension-header');
        header.append(node(document, 'h3', '', title));
        const badge = node(document, 'span', 'tz-dimension-state', dimension.state);
        badge.dataset.state = dimension.state;
        header.append(badge);
        section.append(header);
        const sources = dimension.source?.map(source => ({ google_trends: 'Google Trends', youtube: 'YouTube' })[source] || source).join(', ') || 'No measured source';
        section.append(node(document, 'p', 'tz-dimension-meta',
            sources + ' | ' + windowLabel(dimension.observation_window) + ' | Market: ' + (dimension.market || 'Unavailable')));
        const list = node(document, 'dl', 'tz-component-list');
        const shownReasons = new Set([...(dimension.unavailable_reasons || []), ...(dimension.provisional_reasons || []),
            ...(dimension.quality_warnings || [])]);
        const rows = componentRows(dimension.components || {});
        const extraList = node(document, 'dl', 'tz-component-list');
        for (const [index,row] of rows.entries()) {
            const pair = node(document, 'div', 'tz-component');
            pair.append(node(document, 'dt', '', row.label));
            const value = node(document, 'dd', '', row.value);
            if (row.reason && !shownReasons.has(row.reason)) {
                value.append(node(document, 'span', 'tz-component-reason', row.reason));
                shownReasons.add(row.reason);
            }
            pair.append(value);
            (index < 4 ? list : extraList).append(pair);
        }
        section.append(list);
        if (rows.length > 4) {
            const more = node(document, 'details', 'tz-component-details');
            more.append(node(document, 'summary', '', 'More component values (' + (rows.length - 4) + ')'));
            more.append(extraList); section.append(more);
        }
        const notes = node(document, 'div', 'tz-dimension-notes');
        for (const [title, values] of [['Unavailable reasons', dimension.unavailable_reasons],
            ['Provisional reasons', dimension.provisional_reasons]]) {
            if (!values?.length) continue;
            notes.append(node(document, 'h4', '', title));
            const items = node(document, 'ul');
            for (const value of values) items.append(node(document, 'li', '', value));
            notes.append(items);
        }
        section.append(notes);
        const caveats = {
            demand_momentum: 'Search interest is query-relative, not absolute demand or purchase intent.',
            signal_persistence: 'Search and publication evidence remain separate.',
            content_saturation: 'Publication activity is not validated market saturation. Capped windows cannot establish content growth.',
            creator_diversity: 'Channel counts describe this sample, not population diversity.',
            engagement_velocity: 'Velocity needs repeated snapshots of the same fixed cohort.',
            data_confidence: 'Evidence quality is diagnostic, not validated market truth.'
        };
        section.append(node(document, 'p', 'dimension-caveat', caveats[key]));
        const details = node(document, 'details', 'tz-provenance');
        details.append(node(document, 'summary', '', 'How this is measured'));
        if (dimension.quality_warnings?.length) {
            details.append(node(document, 'h4', '', 'Quality warnings'));
            const warnings = node(document, 'ul');
            dimension.quality_warnings.forEach(value => warnings.append(node(document, 'li', '', value)));
            details.append(warnings);
        }
        details.append(node(document, 'pre', '', JSON.stringify({
            scope: dimension.scope, method_version: dimension.method_version,
            query_id: dimension.query_id, query: dimension.query, retrieval_window: dimension.retrieval_window,
            evidence_identifiers: dimension.evidence_identifiers
        }, null, 2)));
        section.append(details);
        return section;
    }
    function validPayload(payload) {
        return payload?.status === 'success' && typeof payload.query === 'string' &&
            Array.isArray(payload.available_queries) && dimensions.every(([key]) =>
                payload.dimensions?.[key] && states.has(payload.dimensions[key].state) &&
                payload.dimensions[key].components && Array.isArray(payload.dimensions[key].source));
    }
    function mount(section, fetcher = root.fetch.bind(root)) {
        const document = section.ownerDocument;
        const status = section.querySelector('.tz-intelligence-status');
        const error = section.querySelector('.tz-intelligence-error');
        const grid = section.querySelector('.tz-dimensions');
        const control = section.querySelector('.tz-query-control');
        const select = control.querySelector('select');
        let query = 'canonical', sequence = 0, controller;
        async function load() {
            const current = ++sequence;
            controller?.abort();
            controller = new AbortController();
            status.hidden = false;
            status.textContent = 'Loading measured intelligence...';
            error.hidden = true;
            grid.replaceChildren();
            grid.setAttribute('aria-busy', 'true');
            try {
                const response = await fetcher('/api/intelligence/' + encodeURIComponent(section.dataset.intelligenceTopic) +
                    '?query_id=' + encodeURIComponent(query), { signal: controller.signal });
                if (!response.ok) throw new Error('Request failed');
                const payload = await response.json();
                if (current !== sequence) return;
                if (!validPayload(payload) || payload.query_id !== query || payload.topic_id !== section.dataset.intelligenceTopic) {
                    throw new Error('Invalid intelligence response');
                }
                select.replaceChildren();
                for (const choice of payload.available_queries) {
                    const option = node(document, 'option', '', choice.query);
                    option.value = choice.query_id;
                    option.selected = choice.query_id === query;
                    select.append(option);
                }
                control.hidden = false;
                for (const [key, title] of dimensions) grid.append(renderDimension(document, key, title, payload.dimensions[key]));
                status.textContent = 'Measured query: ' + payload.query;
            } catch (failure) {
                if (current !== sequence) return;
                status.hidden = true;
                error.hidden = false;
            } finally {
                if (current === sequence) grid.setAttribute('aria-busy', 'false');
            }
        }
        select.addEventListener('change', () => { query = select.value; load(); });
        section.querySelector('.tz-intelligence-retry').addEventListener('click', load);
        load();
        return { load };
    }
    if (typeof module !== 'undefined' && module.exports) module.exports = { dimensions, humanize, formatValue, componentRows, windowLabel, validPayload };
    if (root.document) for (const section of root.document.querySelectorAll('[data-intelligence-topic]')) mount(section);
})(typeof window !== 'undefined' ? window : globalThis);
