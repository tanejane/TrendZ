const { test } = require('node:test');
const assert = require('node:assert/strict');
const ui = require('../static/js/intelligence.js');

test('six independent titles include Evidence Quality, not a score or lifecycle', () => {
    assert.equal(ui.dimensions.length, 6);
    assert.equal(ui.dimensions.find(([key]) => key === 'data_confidence')[1], 'Evidence Quality');
    assert.equal(new Set(ui.dimensions.map(([key]) => key)).size, 6);
    assert(!ui.dimensions.some(([, title]) => /score|lifecycle|prediction/i.test(title)));
});
test('zero, negatives and missing values remain distinct', () => {
    assert.equal(ui.formatValue(0, 'percent'), '0%');
    assert.equal(ui.formatValue(-100, 'percent'), '-100%');
    assert.equal(ui.formatValue(null), 'Unavailable');
    assert.equal(ui.formatValue(NaN), 'Unavailable');
    assert.equal(ui.formatValue(6.993087, 'percentage_points'), '6.993087 pp');
});
test('nested source components remain separate', () => {
    const rows = ui.componentRows({ search: { persistence: { state: 'available', value: 0.7, unit: 'fraction' } },
        publication: { persistence: { state: 'unavailable', value: null, reason: 'Capped search' } } });
    assert.equal(rows.length, 2);
    assert.equal(rows[0].label, 'Search / Persistence');
    assert.equal(rows[1].value, 'Unavailable');
    assert.equal(rows[1].reason, 'Capped search');
});
test('provisional measured components retain values', () => {
    const [row] = ui.componentRows({ growth: { state: 'provisional', value: 10, unit: 'percent' } });
    assert.equal(row.value, '10%');
    assert.equal(row.state, 'provisional');
});
test('diagnostic strings, arrays and booleans are readable without inventing values', () => {
    assert.equal(ui.formatValue(false), 'No');
    assert.equal(ui.formatValue([]), 'None reported');
    assert.equal(ui.formatValue(['Capped', 'Pending']), 'Capped, Pending');
    assert.equal(ui.humanize('channel_hhi'), 'Channel concentration (HHI)');
});
test('observation windows are UTC and missing windows are explicit', () => {
    assert.equal(ui.windowLabel({ start: '2026-08-19', end: '2026-10-13' }), '19 Aug 2026 to 13 Oct 2026');
    assert.equal(ui.windowLabel({ start: null, end: null }), 'No observation window');
});
test('payload validation rejects missing dimensions and invented states', () => {
    const payload = { status: 'success', query: 'hair oil', available_queries: [], dimensions: Object.fromEntries(
        ui.dimensions.map(([key]) => [key, { state: 'unavailable', source: [], components: {} }])) };
    assert.equal(ui.validPayload(payload), true);
    payload.dimensions.creator_diversity.state = 'validated';
    assert.equal(ui.validPayload(payload), false);
    delete payload.dimensions.creator_diversity;
    assert.equal(ui.validPayload(payload), false);
});
