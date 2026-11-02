// Disposable fixture only; never run against the user's review database.
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const path = require('node:path');
if (process.env.DISPOSABLE_REVIEW_SESSION !== 'yes') throw new Error('Disposable session required');
(async () => {
    const browser = await chromium.launch({channel:'chrome',headless:true});
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors = []; page.on('pageerror',error => errors.push(String(error)));
    try {
        await page.goto(process.env.TEST_REVIEW_URL);
        await page.waitForFunction(() => document.querySelector('#pair-panel').getAttribute('aria-busy')==='false');
        assert.equal(await page.locator('input[name=human_label]:checked').count(),0);
        await page.locator('#batch-panel > summary').click();
        await page.locator('#batch-groups details > summary').first().click();
        assert.equal(await page.locator('.assist-table tbody tr').count(),1);
        page.once('dialog',dialog => dialog.accept());
        await page.locator('[data-accept-topic]').first().click();
        await page.waitForFunction(() => document.querySelector('#progress').textContent.startsWith('1 / 256'));
        await page.selectOption('#status-filter','research');
        await page.waitForFunction(() => document.querySelector('#assist-label').textContent.includes('source_researched'));
        assert.equal(await page.locator('input[name=human_label]:checked').count(),0);
        assert.equal(await page.locator('#assist-sources a').count(),1);
        assert((await page.locator('#assist-evidence').innerText()).includes('<img src=x>'));
        assert.equal(await page.locator('#assist-panel img').count(),0);
        await page.locator('#accept-assist').click();
        await page.waitForFunction(() => document.querySelector('#progress').textContent.startsWith('2 / 256'));
        await page.selectOption('#status-filter','manual');
        await page.waitForFunction(() => document.querySelector('#assist-status').textContent.startsWith('Low confidence'));
        assert.equal(await page.locator('#accept-assist').isDisabled(),true);
        assert.equal(await page.locator('input[name=human_label]:checked').count(),0);
        assert.equal(await page.locator('#generate').isDisabled(),true);
        await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,'assist-desktop.png')});
        await page.setViewportSize({width:390,height:844});
        assert(await page.evaluate(() => document.documentElement.scrollWidth<=innerWidth));
        await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,'assist-mobile.png')});
        assert.deepEqual(errors,[]);
        console.log('PASS: blank human labels, topic batch, research citations/acceptance, XSS escaping, low-confidence block, report gate, desktop/mobile layout; no browser errors');
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode=1; });
