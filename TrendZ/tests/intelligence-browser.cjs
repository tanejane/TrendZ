// Optional browser checks: supply TEST_BASE_URL, PLAYWRIGHT_MODULE and screenshot directory.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:5013';
const output = process.env.SCREENSHOT_DIR || path.join(__dirname, '../reports/phase3b');
const topics = ['niacinamide', 'retinol', 'skin-barrier', 'hair-scalp-care', 'lip-tint', 'glass-skin', 'deepavali-glam', 'hair-oil'];

(async () => {
    await fs.mkdir(output, { recursive: true });
    const browser = await chromium.launch({ channel: 'chrome', headless: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const failures = [];
    page.on('pageerror', error => failures.push(String(error)));
    let checks = 0;
    async function open(topic) {
        await page.goto(base + '/trend-detail/' + topic);
        await page.locator('.tz-dimension').nth(5).waitFor();
        assert.equal(await page.locator('.tz-dimension').count(), 6);
    }
    try {
        for (const topic of topics) {
            await open(topic);
            const expected = await (await fetch(base + '/api/intelligence/' + topic)).json();
            for (const [key, dimension] of Object.entries(expected.dimensions)) {
                const panel = page.locator('[data-dimension="' + key + '"]');
                assert.equal(await panel.locator('.tz-dimension-state').getAttribute('data-state'), dimension.state);
                assert((await panel.innerText()).includes(dimension.source.includes('youtube') ? 'YouTube' : 'Google Trends'));
                await panel.locator('.tz-provenance').evaluate(e => e.open=true);
                for (const warning of dimension.quality_warnings) assert((await panel.innerText()).includes(warning));
                await panel.locator('.tz-provenance').evaluate(e => e.open=false);
            }
            assert.equal(await page.getByRole('heading', { name: 'Evidence Quality', exact: true }).count(), 1);
            assert.equal(await page.getByRole('heading', { name: 'Data Confidence', exact: true }).count(), 0);
            checks++;
        }
        await open('hair-oil');
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: path.join(output, 'desktop-hair-oil.png') });
        assert.equal(await page.locator('.tz-dimension-state[data-state="available"]').count(), 3);
        await page.locator('.tz-provenance summary').first().click();
        assert((await page.locator('.tz-provenance pre').first().innerText()).includes('method_version'));
        checks++;

        await page.selectOption('.tz-query-control select', 'oiling');
        await page.waitForFunction(() => document.querySelector('.tz-intelligence-status').textContent === 'Measured query: hair oiling');
        assert.equal(await page.locator('.tz-query-control select').inputValue(), 'oiling');
        await page.selectOption('.tz-query-control select', 'canonical');
        await page.waitForFunction(() => document.querySelector('.tz-intelligence-status').textContent === 'Measured query: hair oil');
        checks++;

        await page.setViewportSize({ width: 390, height: 844 });
        await open('hair-oil');
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
        const panels = await page.locator('.tz-dimension').evaluateAll(elements => elements.map(e => e.getBoundingClientRect().x));
        assert(panels.every(x => x === panels[0]));
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: path.join(output, 'mobile-hair-oil.png') });
        checks++;

        await page.route('**/api/intelligence/**', route => route.fulfill({ status: 503, body: '{}' }));
        await page.goto(base + '/trend-detail/glass-skin');
        await page.locator('.tz-intelligence-error').waitFor({ state: 'visible' });
        assert.equal(await page.locator('.tz-dimension').count(), 0);
        await page.unroute('**/api/intelligence/**');
        await page.getByRole('button', { name: 'Retry', exact: true }).click();
        await page.locator('.tz-dimension').nth(5).waitFor();
        checks++;

        const payload = await (await fetch(base + '/api/intelligence/glass-skin')).json();
        payload.dimensions.demand_momentum.quality_warnings.push('<img src=x onerror="window.injected=true">');
        await page.route('**/api/intelligence/**', route => route.fulfill({ json: payload }));
        await page.goto(base + '/trend-detail/glass-skin');
        await page.locator('.tz-dimension').nth(5).waitFor();
        assert.equal(await page.locator('.tz-intelligence img').count(), 0);
        assert.equal(await page.evaluate(() => window.injected), undefined);
        checks++;
        await page.unroute('**/api/intelligence/**');
        await open('deepavali-glam');
        await page.locator('.tz-component-details').evaluateAll(es => es.forEach(e => e.open=true));
        assert((await page.locator('[data-dimension="demand_momentum"]').innerText()).includes('No measured Google interest series'));
        assert((await page.locator('[data-dimension="content_saturation"]').innerText()).includes('No defensible saturation benchmark'));
        checks++;
        await page.getByRole('link', { name: 'Open assumption-based ROI scenario' }).click();
        await page.waitForURL('**/roi-insights');
        checks++;
        assert.equal(failures.length, 0, failures.join('\n'));
        console.log(JSON.stringify({ browser_checks_passed: checks, screenshots: output, page_errors: failures }, null, 2));
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
