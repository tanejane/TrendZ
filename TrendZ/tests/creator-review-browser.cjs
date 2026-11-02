// Read-only checks against the initialized real session; no human labels are saved.
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const {chromium}=require('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5016';
const output=process.env.SCREENSHOT_DIR||path.join(__dirname,'../reports/phase5c');
(async()=>{
  await fs.mkdir(output,{recursive:true});
  const browser=await chromium.launch({channel:'chrome',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1100}});
  const errors=[],writes=[];
  page.on('pageerror',error=>errors.push(String(error)));
  page.on('request',request=>{if(request.url().startsWith(base)&&request.method()==='POST')writes.push(request.url());});
  page.on('dialog',dialog=>dialog.accept());
  const initial=await (await fetch(base+'/api/review')).json();
  const loaded=async()=>page.waitForFunction(()=>document.getElementById('workspace').getAttribute('aria-busy')==='false'&&!document.getElementById('content').hidden);
  try {
    await page.goto(base,{waitUntil:'domcontentloaded'});await loaded();
    await page.waitForFunction(()=>document.querySelectorAll('#queue button').length===40);
    assert.equal(await page.locator('#human-label').inputValue(),'');
    assert.equal(await page.locator('#domains input:checked').count(),0);
    assert.equal(await page.locator('#videos input:checked').count(),0);
    assert(await page.locator('#evaluate').isDisabled());
    assert.equal(await page.locator('#profile-progress').innerText(),'0/40');
    assert.equal(await page.locator('#affinity-progress').innerText(),'0/64');
    await page.locator('#use-profile').click();
    assert.equal(await page.locator('#human-label').inputValue(),'');
    assert.equal(await page.locator('#basis').inputValue(),'assisted_review');
    await page.locator('#next').click();await loaded();
    await page.selectOption('#group','review_ready');await loaded();
    assert.equal(await page.locator('#queue button').count(),24);
    await page.selectOption('#group','insufficient');await loaded();
    assert.equal(await page.locator('#queue button').count(),16);
    await page.selectOption('#group','');await loaded();
    await page.locator('#affinity-tab').click();await loaded();
    await page.waitForFunction(()=>document.querySelectorAll('#queue button').length===64);
    assert.equal(await page.locator('#human-label option').count(),6);
    assert(await page.locator('#classification-fields').isHidden());
    assert((await page.locator('#facts').innerText()).includes('No categorical prediction'));
    await page.locator('#use-topic').click();
    assert.equal(await page.locator('#human-label').inputValue(),'');
    await page.locator('#profile-tab').click();await loaded();
    await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(output,'creator-review-desktop.png')});
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
    await page.screenshot({path:path.join(output,'creator-review-mobile.png')});
    await page.locator('#review-form').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(output,'creator-review-mobile-form.png')});
    const exportData=await (await fetch(base+'/api/review/export/affinity')).json();
    assert.equal(exportData.rows.length,64);
    assert(exportData.rows.every(row=>row.review.human_label===null));
    // Inject hostile source strings into a browser-only response, not the saved source/session.
    await page.route('**/api/review/unit?*',async route=>{
      const response=await route.fetch();const data=await response.json();
      data.fixed.display_name='<img src=x onerror="window.__sourceXss=true">';
      data.fixed.videos[0].description='<script>window.__sourceXss=true</script>';
      await route.fulfill({response,json:data});
    });
    await page.reload({waitUntil:'domcontentloaded'});await loaded();
    assert((await page.locator('#creator-name').innerText()).startsWith('<img'));
    assert.equal(await page.evaluate(()=>window.__sourceXss),undefined);
    assert.equal(await page.locator('#creator-name img').count(),0);
    assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
    const final=await (await fetch(base+'/api/review')).json();
    assert.deepEqual(initial.by_type,final.by_type);
    console.log('PASS: profile/affinity units, blank labels, 24/16 groups, draft-only copying, exports, XSS safety, mobile layout; zero POST writes.');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
