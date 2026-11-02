// Deterministic browser checks over frozen local evidence; no external API collection.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:5018';
const output = process.env.SCREENSHOT_DIR || path.join(__dirname, '../reports/phase5e');
const topics = ['niacinamide', 'retinol', 'skin-barrier', 'hair-scalp-care', 'lip-tint', 'glass-skin', 'deepavali-glam', 'hair-oil'];

(async () => {
    await fs.mkdir(output, {recursive: true});
    const browser = await chromium.launch({channel: 'chrome', headless: true});
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errors = [];
    page.on('pageerror', e => errors.push(String(e)));
    // External decorative assets are not test dependencies; existing inline code expects Feather.
    await page.route('https://unpkg.com/feather-icons', r => r.fulfill({contentType: 'application/javascript', body: 'window.feather={replace(){}}'}));
    let checks = 0;
    const root = page.locator('.tz-creators');
    async function open(topic) {
        await page.goto(`${base}/trend-detail/${topic}`);
        await root.locator('form').waitFor({state: 'visible'});
    }
    async function select(product) {
        await root.locator('[name=product_id]').selectOption(product);
        await root.getByRole('button', {name: 'View candidates', exact: true}).click();
        await page.waitForFunction(() => document.querySelector('.tz-creator-results').getAttribute('aria-busy') === 'false');
    }
    try {
        for (const topic of topics) {
            await open(topic);
            const context = await (await fetch(`${base}/api/creator-candidates/context/${topic}`)).json();
            assert.equal(await root.locator('[name=product_id] option').count(), context.products.length + 1);
            assert.equal(await root.locator('.tz-creator-card').count(), 0);
            const product = context.products[0].product_id;
            const expected = await (await fetch(`${base}/api/creator-candidates?${new URLSearchParams({...context.pins, topic_id: topic, query_id: context.query_id, market: context.market, product_id: product})}`)).json();
            await select(product);
            assert.equal(await root.locator('.tz-creator-card').count(), expected.candidates.length);
            assert.deepEqual(await root.locator('.tz-creator-card').evaluateAll(cards => cards.map(c => c.dataset.state)), expected.candidates.map(c => c.candidate_state));
            assert((await root.innerText()).includes('not independent'));
            checks++;
        }
        await open('glass-skin');
        await select('mb-fresh-unspecified');
        const sarthak = root.locator('article').filter({has: page.getByRole('heading', {name: 'Sarthak', exact: true})});
        assert.equal(await sarthak.getAttribute('data-state'), 'qualified_candidate');
        await sarthak.locator('summary').click();
        assert((await sarthak.locator('details').innerText()).includes('assisted_review'));
        assert(await sarthak.locator('details a').count() > 0);
        await select('lp-ha-15ml');
        assert.equal(await sarthak.getAttribute('data-state'), 'manual_review_only');
        checks++;
        await root.locator('[name=required_market_evidence]').selectOption('verified');
        assert.equal(await root.locator('article').count(), 0); // No stale previous context cards.
        await root.getByRole('button', {name: 'View candidates', exact: true}).click();
        await root.locator('article').first().waitFor();
        assert.deepEqual(new Set(await root.locator('article').evaluateAll(a => a.map(e => e.dataset.state))), new Set(['unavailable']));
        checks++;
        await root.locator('[name=required_market_evidence]').selectOption('optional');
        await select('mb-fresh-unspecified');
        await root.scrollIntoViewIfNeeded();
        await page.evaluate(() => window.scrollTo(0, document.querySelector('.tz-creators').getBoundingClientRect().top + window.scrollY - document.querySelector('nav').getBoundingClientRect().height - 16));
        await page.screenshot({path: path.join(output, 'creator-candidates-desktop.png')});
        await page.setViewportSize({width: 390, height: 844});
        assert(await page.evaluate(() => document.querySelector('.tz-creators').getBoundingClientRect().width <= innerWidth));
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        for (const locator of ['.tz-creator-controls', '.tz-creator-card']) {
            assert(await root.locator(locator).evaluateAll(elements => elements.every(e => e.scrollWidth <= e.clientWidth + 1)));
        }
        await page.evaluate(() => window.scrollTo(0, document.querySelector('.tz-creators').getBoundingClientRect().top + window.scrollY - document.querySelector('nav').getBoundingClientRect().height - 16));
        await page.screenshot({path: path.join(output, 'creator-candidates-mobile.png')});
        checks++;
        await page.route('**/api/creator-candidates?*', r => r.fulfill({status: 503, json: {status: 'error', message: 'Fixture evidence unavailable'}}));
        await select('mb-fresh-unspecified');
        assert(await root.locator('[role=alert]').isVisible());
        assert.equal(await root.locator('article').count(), 0);
        await page.unroute('**/api/creator-candidates?*');
        await root.getByRole('button', {name: 'Retry', exact: true}).click();
        await root.locator('article').first().waitFor();
        checks++;
        const context = await (await fetch(`${base}/api/creator-candidates/context/glass-skin`)).json();
        const payload = await (await fetch(`${base}/api/creator-candidates?${new URLSearchParams({...context.pins,topic_id:'glass-skin',query_id:'canonical',market:'MY',product_id:'mb-fresh-unspecified'})}`)).json();
        payload.candidates[0].creator_name = '<img src=x onerror="window.injected=true">';
        payload.candidates[0].channel_url = 'javascript:window.injected=true';
        await page.route('**/api/creator-candidates?*', r => r.fulfill({json: payload}));
        await select('mb-fresh-unspecified');
        assert.equal(await root.locator('img, script').count(), 0);
        assert.equal(await page.evaluate(() => window.injected), undefined);
        assert((await root.locator('article').first().innerText()).includes('<img src=x'));
        checks++;
        assert.deepEqual(errors, []);
        console.log(JSON.stringify({checks, page_errors: errors, screenshots: output}, null, 2));
    } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode = 1;});
