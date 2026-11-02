// Audit the actual measured journey. Scenario inputs below are synthetic assumptions.
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5022';
const output=process.env.SCREENSHOT_DIR||path.join(__dirname,'../portfolio/demo');

(async()=>{
    await fs.mkdir(output,{recursive:true});
    const browser=await chromium.launch({channel:'chrome',headless:true});
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];page.on('pageerror',e=>errors.push(String(e)));
    let checks=0;
    const fitForm=()=>page.locator('.tz-creator-controls');
    async function dashboard(){await page.goto(base+'/');await page.locator('#evidence-topics tr a').first().waitFor();}
    async function shot(file,locator){if(locator)await locator.evaluate(el=>window.scrollTo(0,el.getBoundingClientRect().top+scrollY-84));await page.screenshot({path:path.join(output,file+'.png')});}
    async function noOverflow(){assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
    try{
        await dashboard();
        assert.equal(await page.locator('#tracked-count').innerText(),'18');
        assert((await page.locator('#observed-count').innerText())!=='0');
        assert(!(await page.locator('body').innerText()).includes('AI Trend Forecasting'));
        await shot('hero');await shot('dashboard');checks++;
        const row=page.locator('#evidence-topics tr').filter({has:page.getByRole('link',{name:'Glass Skin',exact:true})});
        if(await row.getByRole('button',{name:'Remove saved'}).count())await row.getByRole('button',{name:'Remove saved'}).click();
        await row.getByRole('button',{name:'Save topic'}).click();await row.getByRole('button',{name:'Remove saved'}).waitFor();
        await page.getByRole('link',{name:'Watchlist',exact:true}).click();
        await page.getByRole('link',{name:'Glass Skin',exact:true}).waitFor();
        await page.getByRole('button',{name:'Remove saved'}).first().click();checks++;
        for(const width of [390,820,1440]){
            await page.setViewportSize({width,height:width===390?844:1000});await dashboard();await noOverflow();
            if(width===390)await shot('dashboard-mobile');
        }checks++;
        await page.getByRole('link',{name:'Glass Skin',exact:true}).click();
        await page.locator('.tz-dimension').nth(5).waitFor();
        assert.equal(await page.locator('.tz-dimension').count(),6);
        assert((await page.locator('.tz-intelligence').innerText()).includes('Evidence Quality'));
        await shot('trend-intelligence',page.locator('.tz-intelligence'));checks++;
        await fitForm().waitFor({state:'visible'});
        await fitForm().locator('[name=product_id]').selectOption('mb-fresh-unspecified');
        await shot('product-fit',page.locator('.tz-creators'));
        await page.getByRole('button',{name:'View candidates',exact:true}).click();
        await page.locator('.tz-creator-card').first().waitFor();
        assert.equal(await page.locator('.tz-creator-card[data-state=unavailable] .tz-campaign-action').count(),0);
        await shot('creator-candidates',page.locator('.tz-creator-card').first());checks++;
        await page.locator('.tz-creator-card[data-state=qualified_candidate] .tz-campaign-action').first().click();
        const form=page.locator('#scenario-form');await form.waitFor({state:'visible'});
        await form.locator('[name=objective]').selectOption('conversion');
        await form.locator('[name=format]').selectOption('short_form_demonstration');
        await form.locator('[name=channel]').selectOption('youtube');
        for(const [name,value]of Object.entries({start_date:'2026-11-01',end_date_exclusive:'2026-12-01',creator_fee:'600',media_spend:'200',production_cost:'150',other_cost:'50',budget_ceiling:'1200',aov:'50',gross_margin:'40',population:'1000',low_rate:'2',base_rate:'5',high_rate:'8'}))await form.locator(`[name=${name}]`).fill(value);
        await form.locator('[name=conversion_basis]').selectOption('assumed_reach');
        const result=page.waitForResponse(r=>r.url().endsWith('/api/campaign-scenarios/evaluate'));
        await form.getByRole('button',{name:'Calculate scenario',exact:true}).click();
        const computed=await(await result).json();
        assert.equal(Number(computed.calculated_outcomes.base.modeled_roi.value),0);
        assert.deepEqual(computed.sensitivity.map(r=>Number(r.modeled_roi.value)),[-0.6,0,0.6]);
        await shot('campaign-scenario',page.locator('#scenario-outcomes'));
        await shot('sensitivity',page.locator('#scenario-sensitivity'));checks++;
        await page.setViewportSize({width:390,height:844});await noOverflow();
        await shot('campaign-mobile',page.locator('#scenario-outcomes'));checks++;
        await page.setViewportSize({width:1440,height:1000});await dashboard();
        await page.route('**/api/trends',r=>r.fulfill({status:503,json:{status:'error'}}));
        await page.getByRole('button',{name:'Refresh evidence',exact:true}).click();
        await page.getByText('Unable to load stored evidence.',{exact:false}).waitFor();
        await page.unroute('**/api/trends');await page.getByRole('button',{name:'Refresh evidence',exact:true}).click();
        await page.locator('#evidence-topics tr a').first().waitFor();checks++;
        const payload=await(await page.request.get(base+'/api/trends')).json();
        payload.trends[0].name='<img src=x onerror="window.injected=true">';
        await page.route('**/api/trends',r=>r.fulfill({json:payload}));
        await page.getByRole('button',{name:'Refresh evidence',exact:true}).click();
        await page.getByRole('link',{name:'<img src=x onerror="window.injected=true">',exact:true}).waitFor();
        assert.equal(await page.locator('#evidence-topics img, #evidence-topics script').count(),0);
        assert.equal(await page.evaluate(()=>window.injected),undefined);await page.unroute('**/api/trends');checks++;
        await page.goto(base+'/trend-detail/sunscreen-reapply');await page.locator('.tz-dimension').nth(5).waitFor();
        assert.equal(await page.locator('.tz-dimension-state[data-state=unavailable]').count(),6);checks++;
        assert.equal((await page.request.get(base+'/trend-detail/no-such-topic')).status(),404);
        assert.equal((await page.request.post(base+'/api/malaysia/chatbot',{data:{question:'hello'}})).status(),410);checks++;
        await page.goto('file:///'+path.resolve(__dirname,'../portfolio/demo/architecture.html').replaceAll('\\','/'));
        await page.setViewportSize({width:1280,height:1200});await shot('architecture');checks++;
        assert.deepEqual(errors,[]);
        await fs.writeFile(path.join(output,'browser_results.json'),JSON.stringify({checks,page_errors:errors,scope:'measured snapshot; scenario inputs synthetic assumptions'},null,2));
        console.log(JSON.stringify({checks,page_errors:errors,screenshots:output},null,2));
    }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
