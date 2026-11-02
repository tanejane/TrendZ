const test = require('node:test');
const assert = require('node:assert/strict');
const {escapeText, safeValues, sourceURL} = require('../static/js/product-text.js');

test('escapes HTML in external product titles, attributes and errors', () => {
    const value = '<img src=x onerror="alert(1)">\'&';
    assert.equal(escapeText(value), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&#39;&amp;');
});
test('source links reject script URLs, credentials and malformed URLs', () => {
    assert.equal(sourceURL('javascript:alert(1)'),'#');
    assert.equal(sourceURL('https://user:pass@example.com/'),'#');
    assert.equal(sourceURL('not a URL'),'#');
    assert.equal(sourceURL('https://example.com/?x=1&y=2'),'https://example.com/?x=1&amp;y=2');
});
test('nested legacy product data escapes once and preserves booleans and counts', () => {
    const result = safeValues({recommended_products:[{product_name:'<script>x</script>',humidity_suitable:false}],
        total_products:1,estimated_cost:null});
    assert.equal(result.recommended_products[0].product_name,'&lt;script&gt;x&lt;/script&gt;');
    assert.equal(result.recommended_products[0].humidity_suitable,false);
    assert.equal(result.total_products,1);
    assert.equal(result.estimated_cost,'Not verified');
});
