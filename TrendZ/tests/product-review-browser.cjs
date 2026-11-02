// Run ONLY against a disposable synthetic review session, never the human review DB.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.TEST_REVIEW_URL;
if (!base || process.env.DISPOSABLE_REVIEW_SESSION !== 'yes') {
    throw new Error('Supply TEST_REVIEW_URL and DISPOSABLE_REVIEW_SESSION=yes for a test-only review server');
}
const output = process.env.SCREENSHOT_DIR || path.join(__dirname,'../reports/phase4c');

(async () => {
    const browser = await chromium.launch({channel:'chrome',headless:true});
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors = []; page.on('pageerror',error => errors.push(String(error)));
    let checks = 0, token, original;
    async function api(url,body,withToken=true) {
        return fetch(base+url,body===undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json',
            ...(withToken ? {'X-Review-Token':token} : {})},body:JSON.stringify(body)});
    }
    try {
        await fs.mkdir(output,{recursive:true});
        await page.goto(base);
        await page.waitForFunction(() => document.querySelector('#pair-panel').getAttribute('aria-busy')==='false');
        token = await page.locator('meta[name=review-token]').getAttribute('content');
        const summary = await (await api('/api/review')).json();
        assert.equal(summary.total,256); assert.equal(summary.labelled,0);
        original = await (await api('/api/review/pair?pair_id='+encodeURIComponent(summary.pairs[0].pair_id))).json();
        assert.equal(await page.locator('input[name=human_label]:checked').count(),0);
        assert.equal(await page.locator('#generate').isDisabled(),true);
        assert((await page.locator('#prediction').innerText()).includes('Predicted:'));
        checks++;

        const note = '<img src=x onerror="window.injected=true"> Synthetic browser note only';
        await page.locator('input[value=no_fit]').check();
        await page.locator('#notes').fill(note);
        await page.locator('#save').click();
        await page.waitForFunction(() => document.querySelector('#message').textContent==='Review saved.');
        assert((await page.locator('#progress').innerText()).startsWith('1 / 256'));
        await page.reload();
        await page.waitForFunction(() => document.querySelector('#pair-panel').getAttribute('aria-busy')==='false');
        await page.locator(`[data-pair-id="${original.pair_id}"]`).click();
        await page.waitForFunction(id => document.querySelector('#pair-id').textContent.startsWith(id),original.pair_id);
        assert.equal(await page.locator('input[name=human_label]:checked').inputValue(),'no_fit');
        assert.equal(await page.locator('#notes').inputValue(),note);
        assert.equal(await page.locator('#pair-panel img').count(),0);
        checks++;
        const stale = await api('/api/review/label',{pair_id:original.pair_id,human_label:'direct_fit',notes:'',revision:0});
        assert.equal(stale.status,409);
        const noToken = await api('/api/review/label',{pair_id:original.pair_id,human_label:'direct_fit',revision:1},false);
        assert.equal(noToken.status,403);
        checks++;

        await page.selectOption('#status-filter','pending');
        await page.waitForFunction(id => !document.querySelector('#pair-id').textContent.startsWith(id),original.pair_id);
        for (const topic of summary.topics) {
            await page.selectOption('#topic-filter',topic.topic_id);
            await page.waitForFunction(topic => document.querySelector('#pair-id').textContent.startsWith(topic+'/'),topic.topic_id);
            assert.equal(await page.locator('input[name=human_label]:checked').count(),0);
            assert((await page.locator('#product-facts').innerText()).includes('Application area'));
            const urls = await page.locator('#sources a').evaluateAll(links => links.map(a => a.href));
            assert(urls.every(url => url.startsWith('https://')));
            checks++;
        }
        await page.selectOption('#topic-filter','lip-tint');
        await page.waitForFunction(() => document.querySelector('#pair-id').textContent.startsWith('lip-tint/'));
        const match = summary.pairs.find(pair => pair.topic_id==='lip-tint' && pair.predicted_fit_state==='direct_fit');
        await page.locator(`[data-pair-id="${match.pair_id}"]`).click();
        await page.waitForFunction(id => document.querySelector('#pair-id').textContent.startsWith(id),match.pair_id);
        assert.equal(await page.locator('#explanation').inputValue(),'');
        assert.equal(await page.locator('input[name=human_label]:checked').count(),0);
        const pending = await api('/api/review/finalize',{});
        assert.equal(pending.status,409);
        const pendingBody = await pending.json();
        assert.equal(pendingBody.metrics,null); assert.equal(pendingBody.recommendation,null);
        checks++;
        await page.screenshot({path:path.join(output,'review-desktop.png')});
        await page.setViewportSize({width:390,height:844});
        assert(await page.evaluate(() => document.documentElement.scrollWidth<=window.innerWidth));
        await page.screenshot({path:path.join(output,'review-mobile.png')});
        checks++;

        const payload = await (await api('/api/review/pair?pair_id='+encodeURIComponent(match.pair_id))).json();
        payload.prediction.provenance.product.product_name = '<img src=x onerror="window.injected=true">';
        payload.prediction.supporting_evidence.forEach(ref => {ref.source.url='javascript:window.injected=true';});
        await page.route('**/api/review/pair?*',route => route.fulfill({json:payload}));
        await page.locator(`[data-pair-id="${match.pair_id}"]`).click();
        await page.waitForFunction(() => document.querySelector('#product-name').textContent.startsWith('<img'));
        assert.equal(await page.locator('#pair-panel img').count(),0);
        assert.equal(await page.locator('#sources a').count(),0);
        assert.equal(await page.evaluate(() => Boolean(window.injected)),false);
        checks++;
        assert.deepEqual(errors,[]);
        console.log(JSON.stringify({checks,page_errors:errors,session:'disposable synthetic DB only'},null,2));
    } finally {
        if (original && token) {
            const row = await (await api('/api/review/pair?pair_id='+encodeURIComponent(original.pair_id))).json();
            if (row.human_label !== null) await api('/api/review/label',{
                pair_id:original.pair_id,human_label:null,notes:'',unsupported_explanation:null,reset:true,revision:row.revision});
        }
        await browser.close();
    }
})().catch(error => {console.error(error);process.exitCode=1;});
