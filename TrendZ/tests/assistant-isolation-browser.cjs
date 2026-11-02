const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:5020';
const output = process.env.SCREENSHOT_DIR || path.join(__dirname, '../reports/phase7b/isolation');

(async () => {
    await fs.mkdir(output, {recursive: true});
    const browser = await chromium.launch({channel: 'chrome', headless: true});
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    let checks = 0;
    try {
        const response = await page.request.post(base + '/api/malaysia/chatbot', {
            data: {question: '<img src=x onerror=alert(1)>', topic_id: 'unknown-topic'}
        });
        assert.equal(response.status(), 410);
        const payload = await response.json();
        assert.equal(payload.code, 'legacy_assistant_retired');
        assert(!JSON.stringify(payload).includes('<img'));
        checks++;
        for (const [name, width, height] of [['desktop',1440,1000],['mobile',390,844]]) {
            await page.setViewportSize({width, height});
            await page.goto(base + '/');
            await page.locator('.assistant-small').focus();
            await page.locator('#assistant-status').waitFor();
            assert((await page.locator('#assistant-status').innerText()).includes('No AI/model is connected'));
            assert.equal(await page.locator('#chatbot-popup, #chatbot-input, #chatbot-form').count(), 0);
            assert.equal(await page.getByRole('button', {name: /Ask TrendZ AI|Ask AI/i}).count(), 0);
            await page.screenshot({path: path.join(output, name + '.png'), fullPage: true});
            checks++;
        }
        await page.goto(base + '/trend-detail/glass-skin');
        await page.locator('.assistant-small').focus();
        assert((await page.locator('body').innerText()).includes('No AI/model is connected'));
        assert.equal(await page.locator('[onclick*="askAI"]').count(), 0);
        assert.deepEqual(errors, []);
        checks++;
        const result = {checks, page_errors: errors, legacy_status: 410, model_connected: false};
        await fs.writeFile(path.join(output, 'results.json'), JSON.stringify(result, null, 2));
        console.log(JSON.stringify(result, null, 2));
    } finally {
        await browser.close();
    }
})().catch(error => {console.error(error); process.exitCode = 1;});
