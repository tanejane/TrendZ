const test = require('node:test');
const assert = require('node:assert/strict');
const {format, safeSource, pending} = require('../static/js/product-review.js');

test('review values distinguish missing, empty and zero', () => {
    assert.equal(format(null),'Not recorded');
    assert.equal(format([]),'None recorded');
    assert.equal(format(0),'0');
});
test('only HTTPS source links without credentials are allowed', () => {
    assert.equal(safeSource('javascript:alert(1)'),null);
    assert.equal(safeSource('https://user:pass@example.com/'),null);
    assert.equal(safeSource('https://example.com/'),'https://example.com/');
});
test('pending is based on HUMAN labels and independent evidence check, never prediction', () => {
    assert.equal(pending({human_label:null,predicted_fit_state:'direct_fit'}),true);
    assert.equal(pending({human_label:'no_fit',pending_explanation:true}),true);
    assert.equal(pending({human_label:'direct_fit',pending_explanation:false}),false);
});
