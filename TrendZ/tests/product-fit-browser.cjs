// Optional integration checks; requires an already running local Flask server.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:5013';
const output = process.env.SCREENSHOT_DIR || path.join(__dirname, '../reports/phase4b');
const topics = ['niacinamide','retinol','skin-barrier','hair-scalp-care','lip-tint','glass-skin','deepavali-glam','hair-oil'];

(async () => {
    await fs.mkdir(output,{recursive:true});
    const browser = await chromium.launch({channel:'chrome',headless:true});
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors = [];
    page.on('pageerror',error => errors.push(String(error)));
    let checks = 0;
    async function search(query) {
        await page.locator('#hashtagInput').fill(query);
        await page.locator('.btn-search').click();
        await page.locator('#results .trend-info, #results .error').waitFor();
    }
    try {
        await page.goto(base+'/hashtag-products');
        for (const topic of topics) {
            const api = await (await fetch(base+'/api/product-fit/'+topic)).json();
            await search(topic);
            assert.equal(await page.locator('.product-card').count(),api.matched_products.length);
            const text = await page.locator('#results').innerText();
            assert(!text.includes('undefined'));
            assert(!text.includes('RM null'));
            assert(text.includes('Not verified'));
            assert(text.includes(api.catalogue_version));
            checks++;
        }
        await search('glassskin');
        assert.notEqual(await page.locator('.trend-info').evaluate(el => getComputedStyle(el).color),'rgb(255, 255, 255)');
        await page.screenshot({path:path.join(output,'product-fit-desktop.png'),fullPage:false});
        await page.setViewportSize({width:390,height:844});
        assert(await page.evaluate(() => document.documentElement.scrollWidth<=window.innerWidth));
        await page.screenshot({path:path.join(output,'product-fit-mobile.png'),fullPage:false});
        checks++;
        await search('unconfigured-topic');
        assert((await page.locator('#results .error').innerText()).includes('No configured Product Fit'));
        checks++;

        const payload = await (await fetch(base+'/api/malaysia/hashtag-products/glassskin')).json();
        payload.recommendations.recommended_products[0].product_name = '<img src=x onerror="window.injected=true">';
        payload.recommendations.recommended_products[0].source_url = 'javascript:window.injected=true';
        await page.route('**/api/malaysia/hashtag-products/**', route => route.fulfill({json:payload}));
        await search('<script>window.injected=true</script>');
        assert.equal(await page.locator('#results img, #results script').count(),0);
        assert.equal(await page.evaluate(() => Boolean(window.injected)),false);
        assert.equal(await page.locator('.product-card a').first().getAttribute('href'),'#');
        assert((await page.locator('.product-card').first().innerText()).includes('<img src=x'));
        checks++;
        assert.deepEqual(errors,[]);
        console.log(JSON.stringify({checks,page_errors:errors,screenshots:output},null,2));
    } finally {
        await browser.close();
    }
})().catch(error => {console.error(error);process.exitCode=1;});
