(function () {
    'use strict';
    function format(value) {
        if (value === null || value === undefined) return 'Not recorded';
        if (Array.isArray(value)) return value.length ? value.map(format).join(', ') : 'None recorded';
        return typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value);
    }
    function safeSource(value) {
        try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : null; }
        catch (_) { return null; }
    }
    function pending(pair) { return pair.human_label === null || pair.pending_explanation; }
    function assistQueue(pair, queue) {
        if (pair.human_label !== null) return false;
        if (queue === 'manual') return pair.assist_manual_required === true;
        return !pair.assist_manual_required && pair.assist_source ===
            (queue === 'prescreen' ? 'assisted_prescreen' : 'source_researched');
    }
    if (typeof module !== 'undefined') module.exports = {format, safeSource, pending, assistQueue};
    if (typeof document === 'undefined') return;

    const $ = id => document.getElementById(id);
    const token = document.querySelector('meta[name=review-token]').content;
    let summary, current, dirty = false, busy = false, loadSequence = 0, reportURL;
    let activeTopic = '', activeQueue = 'all';
    function message(text) { $('message').textContent = text || ''; }
    async function api(path, body) {
        const response = await fetch(path, body === undefined ? {} : {
            method:'POST', headers:{'Content-Type':'application/json','X-Review-Token':token}, body:JSON.stringify(body)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.message || data.reason || 'The review could not be saved');
        return data;
    }
    function visiblePairs() {
        return summary.pairs.filter(pair => (!activeTopic || pair.topic_id === activeTopic) &&
            (activeQueue === 'all' || (activeQueue === 'pending' && pair.human_label === null) ||
             (activeQueue === 'evidence' && pair.pending_explanation) ||
             (['prescreen','research','manual'].includes(activeQueue) && assistQueue(pair, activeQueue)) ||
             (activeQueue === 'labelled' && pair.human_label !== null)));
    }
    function canLeave() { return !dirty || window.confirm('Discard unsaved changes for this pair?'); }
    function paintSummary() {
        $('progress').textContent = `${summary.labelled} / ${summary.total} fit labels saved. ${summary.pending} pending.`;
        $('completion').value = summary.labelled;
        $('evidence-progress').textContent = `${summary.pending_explanation_checks} explanation checks pending`;
        $('provenance').textContent = `${summary.catalogue_version} | ${summary.method_version} | Session ${summary.session_id}`;
        $('generate').disabled = !summary.ready || busy;
        $('report-status').textContent = summary.stale ? 'Source or method files changed. This session is read-only; preserve it for provenance.' :
            summary.ready ? 'All human judgments are complete. Validation report is ready to generate.' :
            'Validation metrics and recommendations remain pending until all 256 fit labels and predicted-match evidence checks are saved.';
        const selected = $('topic-filter').value;
        $('topic-filter').replaceChildren(new Option('All topics', ''));
        summary.topics.forEach(topic => $('topic-filter').add(new Option(`${topic.name} (${topic.labelled}/${topic.total})`,topic.topic_id)));
        $('topic-filter').value = selected;
        paintAssistGroups();
        paintQueue();
    }
    function paintAssistGroups() {
        $('assist-progress').textContent = `${summary.pairs.filter(p => assistQueue(p,'prescreen')).length} pre-screen acceptances, `+
            `${summary.pairs.filter(p => assistQueue(p,'research')).length} researched acceptances, `+
            `${summary.pairs.filter(p => assistQueue(p,'manual')).length} low-confidence manual reviews pending.`;
        $('batch-groups').replaceChildren();
        summary.topics.forEach(topic => {
            const rows = summary.pairs.filter(p => p.topic_id === topic.topic_id && p.assist_source === 'assisted_prescreen');
            if (!rows.length) return;
            const group = document.createElement('details'), heading = document.createElement('summary');
            heading.textContent = `${topic.name}: ${rows.filter(p => p.human_label === null).length} pending / ${rows.length} suggestions`;
            const button = document.createElement('button'); button.type = 'button';
            button.textContent = 'Accept pending suggestions for '+topic.name;
            button.dataset.acceptTopic = topic.topic_id;
            button.disabled = busy || summary.stale || !rows.some(p => p.human_label === null);
            button.onclick = () => acceptSuggestions(topic.topic_id);
            const wrap = document.createElement('div'); wrap.className = 'assist-table-wrap';
            const table = document.createElement('table'); table.className = 'assist-table';
            const head = table.createTHead().insertRow();
            ['Product','Machine prediction','Pre-screen suggestion','CSV reason','Human label','Review'].forEach(title => {
                const th = document.createElement('th'); th.scope = 'col'; th.textContent = title; head.append(th);
            });
            const body = table.createTBody();
            rows.forEach(pair => {
                const tr = body.insertRow();
                [pair.product_name,pair.predicted_fit_state,pair.assist_label,pair.assist_evidence,pair.human_label || 'Pending'].forEach(text => {
                    tr.insertCell().textContent = text;
                });
                const edit = document.createElement('button'); edit.type = 'button'; edit.textContent = 'Inspect / edit';
                edit.onclick = async () => {
                    if (busy || !canLeave()) return;
                    activeTopic = topic.topic_id; activeQueue = 'all';
                    $('topic-filter').value = activeTopic; $('status-filter').value = activeQueue;
                    try { await openPair(pair.pair_id); $('product-name').scrollIntoView({block:'start'}); }
                    catch (error) { message(error.message); }
                };
                tr.insertCell().append(edit);
            });
            wrap.append(table); group.append(heading,button,wrap); $('batch-groups').append(group);
        });
    }
    async function acceptSuggestions(topic) {
        if (busy || !canLeave()) return;
        const rows = topic ? summary.pairs.filter(p => p.topic_id === topic && assistQueue(p,'prescreen')) :
            current && current.human_label === null && current.assist_source && !current.assist_manual_required ? [current] : [];
        if (!rows.length) return;
        if (topic && !window.confirm(`Accept ${rows.length} pre-screen suggestions for ${topic} as your human-approved labels? Explanation checks remain separate.`)) return;
        const identifier = current?.pair_id;
        busy = true; paintSummary();
        $('review-form').inert = true;
        $('accept-assist').disabled = true;
        try {
            const result = await api('/api/review/accept-assist',{
                approvals:rows.map(p => ({pair_id:p.pair_id,revision:p.revision,assist_id:p.assist_id})),
                ...(topic ? {topic_id:topic} : {}), reviewer:$('reviewer').value || null});
            summary = result.progress; dirty = false; invalidateReport();
            busy = false; paintSummary();
            const candidates = visiblePairs();
            const next = candidates.find(p => p.pair_id !== identifier && p.human_label === null);
            if (next || identifier) await openPair(next?.pair_id || identifier);
            message(`${result.result.accepted.length} human labels accepted. Explanation checks remain independent.`);
        } catch (error) { message(error.message); }
        finally { busy = false; $('review-form').inert = false; paintSummary(); if (current) renderPair(); }
    }
    function paintQueue() {
        const pairs = visiblePairs();
        $('queue-count').textContent = `${pairs.length} pairs in this queue`;
        $('pair-list').replaceChildren();
        pairs.forEach(pair => {
            const button = document.createElement('button'); button.type = 'button';
            button.dataset.pairId = pair.pair_id;
            button.textContent = pair.product_name;
            button.setAttribute('aria-current', String(current?.pair_id === pair.pair_id));
            const label = document.createElement('span'); label.className = 'queue-label';
            label.textContent = `${pair.topic_id} | Human: ${pair.human_label || 'unlabelled'}${pair.assist_manual_required ? ' | Manual review required' : pair.assist_source ? ' | '+pair.assist_source : ''}${pair.pending_explanation ? ' | Evidence pending' : ''}`;
            button.append(label);
            button.onclick = () => { if (!busy && canLeave()) openPair(pair.pair_id).catch(error => message(error.message)); };
            $('pair-list').append(button);
        });
        const index = pairs.findIndex(pair => pair.pair_id === current?.pair_id);
        $('previous').disabled = busy || index <= 0;
        $('next').disabled = busy || index < 0 || index >= pairs.length-1;
    }
    function textList(id, values, empty) {
        $(id).replaceChildren();
        (values?.length ? values : [empty]).forEach(value => {
            const item = document.createElement('li'); item.textContent = format(value); $(id).append(item);
        });
    }
    function sourceLink(container, url, label) {
        const safe = safeSource(url);
        if (!safe) return;
        const link = document.createElement('a'); link.href = safe; link.target = '_blank';
        link.rel = 'noopener noreferrer'; link.textContent = label || url; container.append(link);
    }
    function renderPair() {
        const prediction = current.prediction, product = prediction.provenance.product;
        const ingredients = prediction.dimensions.ingredient_agreement;
        $('topic-name').textContent = `${current.context.canonical_topic} | ${current.context.query} | ${current.context.market}`;
        $('product-name').textContent = product.product_name;
        $('prediction').textContent = `Predicted: ${prediction.fit_state}`;
        $('pair-id').textContent = `${current.pair_id} | ${current.fixed.split} | revision ${current.revision}`;
        $('assist-panel').hidden = !current.assist_source;
        $('assist-label').textContent = `${current.assist_source || ''} | ${current.assist_label || ''} | ${current.assist_confidence || ''} confidence`;
        $('assist-evidence').textContent = current.assist_evidence || '';
        $('assist-uncertainty').textContent = current.assist_uncertainty || '';
        $('assist-sources').replaceChildren();
        (current.assist_source_urls || []).forEach(url => {
            const li = document.createElement('li'); sourceLink(li,url); $('assist-sources').append(li);
        });
        $('assist-status').textContent = current.human_label !== null ?
            `Saved label basis: ${current.label_provenance?.source || 'human approval'}.` :
            current.assist_manual_required ? 'Low confidence: pending manual review. Quick acceptance is disabled.' :
            'Suggestion only. No human-approved label until you accept or save your own label.';
        $('accept-assist').disabled = busy || summary.stale || current.human_label !== null || !!current.assist_manual_required;
        const facts = [
            ['Brand',product.brand], ['Category / subcategory',`${product.category} / ${product.subcategory}`],
            ['Format',product.product_format], ['Application area',product.application_area],
            ['Variant / shade / size',[product.variant, product.shade, product.size].filter(value => value !== null)],
            ['Intent ingredients',ingredients.requested], ['Matched ingredients',ingredients.matched],
            ['Listed ingredient count',product.normalized_ingredients === null ? null : product.normalized_ingredients.length], ['INCI completeness',product.ingredient_completeness],
            ['Declared benefits',(product.manufacturer_claims || []).map(claim => `${claim.concept}: ${claim.text} (source claim, not independent verification)`)]];
        $('product-facts').replaceChildren();
        facts.forEach(([label,value]) => {
            const dt = document.createElement('dt'); dt.textContent = label;
            const dd = document.createElement('dd'); dd.textContent = format(value);
            $('product-facts').append(dt,dd);
        });
        $('intent').textContent = JSON.stringify(current.context.intent,null,2);
        $('quality').textContent = JSON.stringify({warnings:prediction.warnings,raw_ingredients:product.raw_ingredients,
            normalized_ingredients:product.normalized_ingredients,
            field_quality:product.field_quality,catalogue_version:prediction.provenance.catalogue_version},null,2);
        textList('missing',prediction.missing_evidence,'No missing evidence recorded by this method');
        textList('contradictions',prediction.contradictions,'No contradictions recorded by this method');
        $('supporting').replaceChildren();
        prediction.supporting_evidence.forEach(ref => {
            const entry = document.createElement('details'); entry.className = 'evidence-entry';
            const field = document.createElement('summary'); field.textContent = ref.field+' ('+ref.field_state+')';
            const value = document.createElement('p'); value.textContent = format(ref.value);
            const basis = document.createElement('p'); basis.textContent = `${ref.basis} | ${ref.field_state} | ${ref.catalogue_version} | ${ref.source.verified_on}`;
            entry.append(field,value,basis); sourceLink(entry,ref.source.url,'Source: '+ref.source_id);
            $('supporting').append(entry);
        });
        if (!prediction.supporting_evidence.length) $('supporting').textContent = 'No source-backed fields recorded.';
        $('sources').replaceChildren();
        [...new Set(prediction.supporting_evidence.map(ref => ref.source.url))].forEach(url => {
            const li = document.createElement('li'); sourceLink(li,url); $('sources').append(li);
        });
        document.querySelectorAll('input[name=human_label]').forEach(input => { input.checked = input.value === current.human_label; });
        const match = ['direct_fit','supporting_fit'].includes(prediction.fit_state);
        $('explanation-field').hidden = !match;
        $('explanation').value = current.unsupported_explanation === null ? '' : current.unsupported_explanation ? 'unsupported' : 'supported';
        $('notes').value = current.notes;
        $('reviewer').value = current.reviewer || '';
        $('save-status').textContent = current.reviewed_on ? `Saved ${current.reviewed_on} | ${current.label_provenance?.source || 'human approval'}` : 'No human label saved for this pair.';
        ['save','save-next','clear'].forEach(id => { $(id).disabled = summary.stale || busy; });
        $('pair-panel').setAttribute('aria-busy','false');
        dirty = false;
        paintQueue();
    }
    async function openPair(identifier) {
        const sequence = ++loadSequence;
        $('pair-panel').setAttribute('aria-busy','true');
        $('review-form').inert = true;
        const row = await api('/api/review/pair?pair_id='+encodeURIComponent(identifier));
        if (sequence !== loadSequence) return;
        current = row; $('pair-panel').hidden = false; renderPair(); $('review-form').inert = false;
    }
    function invalidateReport() {
        if (reportURL) URL.revokeObjectURL(reportURL);
        reportURL = null; $('download-report').hidden = true; $('report-preview').hidden = true;
    }
    async function save(next=false, reset=false) {
        if (busy || !current) return;
        const checked = document.querySelector('input[name=human_label]:checked');
        if (!reset && !checked) { message('Choose a human fit label. The prediction is not copied into your label.'); return; }
        if (reset && !window.confirm('Clear the saved review for this pair? Its revision history will be preserved.')) return;
        busy = true; message('Saving...');
        ['save','save-next','clear','next','previous','topic-filter','status-filter'].forEach(id => { $(id).disabled = true; });
        try {
            const result = await api('/api/review/label', {pair_id:current.pair_id,revision:current.revision,
                human_label:reset ? null : checked.value, notes:reset ? '' : $('notes').value,
                unsupported_explanation:reset || $('explanation-field').hidden || !$('explanation').value ? null : $('explanation').value === 'unsupported',
                reviewer:$('reviewer').value || null, reset});
            summary = result.progress; dirty = false; invalidateReport();
            const identifier = current.pair_id;
            busy = false; paintSummary();
            const candidates = visiblePairs();
            const index = candidates.findIndex(pair => pair.pair_id === identifier);
            const remaining = [...candidates.slice(index+1),...candidates.slice(0,index+1)].filter(pair => pair.pair_id !== identifier && pending(pair));
            await openPair(next && remaining.length ? remaining[0].pair_id : identifier);
            message('Review saved.');
        } catch (error) { message(error.message); }
        finally {
            busy = false;
            ['topic-filter','status-filter'].forEach(id => { $(id).disabled = false; });
            ['save','save-next','clear'].forEach(id => { $(id).disabled = summary.stale; });
            paintQueue();
        }
    }
    async function changeFilter() {
        if (busy || !canLeave()) { $('topic-filter').value = activeTopic; $('status-filter').value = activeQueue; return; }
        activeTopic = $('topic-filter').value; activeQueue = $('status-filter').value;
        const pairs = visiblePairs(); paintQueue();
        if (pairs.length) await openPair(pairs[0].pair_id);
        else { $('pair-panel').hidden = true; message('No pairs in this queue. Change the filter to continue.'); }
    }
    $('topic-filter').onchange = () => changeFilter().catch(error => message(error.message));
    $('status-filter').onchange = () => changeFilter().catch(error => message(error.message));
    $('review-form').onsubmit = event => { event.preventDefault(); save(); };
    $('save-next').onclick = () => save(true);
    $('clear').onclick = () => save(false,true);
    $('accept-assist').onclick = () => acceptSuggestions();
    $('edit-assist').onclick = () => document.querySelector('input[name=human_label]').focus();
    $('previous').onclick = () => navigate(-1);
    $('next').onclick = () => navigate(1);
    function navigate(offset) {
        const pairs = visiblePairs(), index = pairs.findIndex(pair => pair.pair_id === current?.pair_id);
        if (!busy && pairs[index+offset] && canLeave()) openPair(pairs[index+offset].pair_id).catch(error => message(error.message));
    }
    $('review-form').oninput = () => { dirty = true; };
    window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
    $('generate').onclick = async () => {
        if (busy || dirty) { message('Save the current review before generating a report.'); return; }
        $('generate').disabled = true; message('Generating validation report...');
        try {
            const report = await api('/api/review/finalize',{});
            invalidateReport();
            reportURL = URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));
            $('download-report').href = reportURL; $('download-report').hidden = false;
            $('report-preview').textContent = JSON.stringify({metrics:report.metrics.macro_ranking,
                confusion_matrix:report.metrics.confusion_matrix,recommendation:report.recommendation},null,2);
            $('report-preview').hidden = false; message('Validation report generated from completed human judgments.');
        } catch (error) { message(error.message); }
        finally { $('generate').disabled = !summary.ready; }
    };
    (async () => {
        summary = await api('/api/review'); paintSummary();
        const first = summary.pairs.find(pending) || summary.pairs[0];
        if (first) await openPair(first.pair_id);
    })().catch(error => { message('Unable to load review session: '+error.message); $('product-name').textContent = 'Review unavailable'; });
})();
