const {test} = require('node:test');
const assert = require('node:assert/strict');
const {assistQueue} = require('../static/js/product-review.js');
test('assist queues separate research, prescreen and low-confidence manual rows', () => {
    const row = {human_label:null,assist_source:'source_researched',assist_manual_required:false};
    assert.equal(assistQueue(row,'research'),true);
    assert.equal(assistQueue(row,'prescreen'),false);
    assert.equal(assistQueue({...row,assist_manual_required:true},'research'),false);
    assert.equal(assistQueue({...row,assist_manual_required:true},'manual'),true);
    assert.equal(assistQueue({...row,human_label:'no_fit'},'research'),false);
    assert.equal(assistQueue({...row,assist_source:'assisted_prescreen'},'prescreen'),true);
});
