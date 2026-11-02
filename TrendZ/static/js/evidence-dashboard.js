(() => {
    const grid=document.querySelector('#trend-grid');
    if(!grid)return;
    const status=document.querySelector('#dashboard-status'),reload=document.querySelector('#reload');
    const search=document.querySelector('#trend-search');
    const savedOnly=document.body.dataset.savedOnly==='true';
    const fields=[['demand_momentum','Demand Momentum'],['signal_persistence','Signal Persistence'],['content_saturation','Content Saturation'],['data_confidence','Evidence Quality']];
    let topics=[],saved=new Set(),category='',generation=0,controller;
    const intelligence=new Map(),failed=new Set(),pendingSaves=new Set();
    function node(tag,text,parent,cls){const el=document.createElement(tag);if(text!=null)el.textContent=text;if(cls)el.className=cls;parent?.append(el);return el;}
    function icon(name,parent){const el=node('i',null,parent);el.dataset.feather=name;el.setAttribute('aria-hidden','true');}
    function icons(){window.feather?.replace();}
    async function read(url,options){const r=await fetch(url,options);const data=await r.json();if(!r.ok||data.status==='error')throw new Error('Evidence could not be retrieved');return data;}
    function date(value){if(!value)return 'Date unavailable';return new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(value+'T00:00:00Z'));}
    function card(topic){
        const item=node('article',null,grid,'trend-card');item.dataset.topic=topic.id;item.dataset.category=topic.category;
        const image=node('div',null,item,'trend-card-image');image.dataset.category=topic.category;image.setAttribute('aria-hidden','true');
        const save=node('button',null,item,'save-trend icon-button');save.type='button';save.setAttribute('aria-pressed',String(saved.has(topic.id)));
        save.setAttribute('aria-label',saved.has(topic.id)?'Remove '+topic.name+' from watchlist':'Save '+topic.name);save.title=save.getAttribute('aria-label');icon('bookmark',save);
        save.disabled=pendingSaves.has(topic.id);
        save.addEventListener('click',async()=>{
            save.disabled=true;pendingSaves.add(topic.id);
            try{
                const removing=saved.has(topic.id);
                await read('/api/watchlist/'+(removing?'remove':'add'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({trend_id:topic.id})});
                removing?saved.delete(topic.id):saved.add(topic.id);pendingSaves.delete(topic.id);render();
                status.textContent=removing?'Removed from your watchlist.':'Saved to your watchlist.';
            }catch(_){pendingSaves.delete(topic.id);render();status.textContent='Watchlist update failed. Please retry.';}
        });
        const body=node('div',null,item,'trend-card-body');
        const meta=node('div',null,body,'trend-card-meta');node('span',topic.category,meta);node('span',topic.market,meta);
        const heading=node('h3',null,body);const title=node('a',topic.name,heading);title.href='/trend-detail/'+encodeURIComponent(topic.id);
        const payload=intelligence.get(topic.id);
        const windows=payload?Object.values(payload.dimensions).map(d=>d.observation_window?.end).filter(Boolean).sort():[];
        node('p',windows.length?'Observed to '+date(windows.at(-1)):'Stored observations · dates loading',body,'trend-asof');
        const states=node('dl',null,body,'card-states');
        for(const [key,label]of fields){
            const row=node('div',null,states);node('dt',label,row);
            const d=payload?.dimensions?.[key];
            const state=d?.state||(failed.has(topic.id)?'not_loaded':'loading');
            const badge=node('dd',state.replaceAll('_',' '),row,'evidence-badge');badge.dataset.state=state;
            badge.title=d?[...(d.unavailable_reasons||[]),...(d.provisional_reasons||[]),...(d.quality_warnings||[])].join(' '):'Not retrieved yet; this is not a source-unavailable finding.';
        }
        const foot=node('div',null,body,'trend-card-footer');
        const link=node('a','Explore Trend',foot);link.href=title.href;icon('arrow-right',link);
        node('span','Canonical query',foot);
        if(failed.has(topic.id)){const retry=node('button','Retry states',body,'inline-retry');retry.type='button';retry.addEventListener('click',()=>loadStates([topic],generation,controller.signal));}
    }
    function render(){
        grid.replaceChildren();
        const observed=topics.filter(t=>t.data_mode==='real');
        const collection=savedOnly?topics.filter(t=>saved.has(t.id)):observed;
        const visible=collection.filter(t=>(!category||t.category===category)&&t.name.toLowerCase().includes(search.value.trim().toLowerCase()));
        visible.forEach(card);
        document.querySelector('#observed-count').textContent=collection.length;
        document.querySelector('#watchlist-empty').hidden=!savedOnly||saved.size>0;
        document.querySelector('#filtered-empty').hidden=visible.length>0||(savedOnly&&saved.size===0);
        document.querySelector('.category-tabs').hidden=savedOnly&&saved.size===0;
        document.querySelector('.discover-actions').hidden=savedOnly&&saved.size===0;
        status.textContent=visible.length?visible.length+' '+(savedOnly?'saved':'observed')+' trends.':'';
        const awaiting=document.querySelector('#awaiting-topics');
        if(awaiting){
            awaiting.replaceChildren();const pending=topics.filter(t=>t.data_mode!=='real');
            document.querySelector('#awaiting-count').textContent=pending.length+' topics';
            for(const t of pending){const a=node('a',t.name,awaiting);a.href='/trend-detail/'+encodeURIComponent(t.id);}
        }
        document.querySelector('#tracked-count').textContent=topics.length+' configured topics; '+observed.length+' with observations. Automatic alerts are not implemented.';
        icons();
    }
    async function loadStates(rows,current,signal){
        // Sequential batches bound UI requests; these read stored data, not source APIs.
        for(let index=0;index<rows.length;index+=3){
            await Promise.all(rows.slice(index,index+3).map(async t=>{
                try{
                    const data=await read('/api/intelligence/'+encodeURIComponent(t.id)+'?query_id=canonical',{signal});
                    if(current!==generation)return;
                    if(data.topic_id!==t.id||data.query_id!=='canonical'||!fields.every(([key])=>['available','provisional','unavailable'].includes(data.dimensions?.[key]?.state)))throw new Error('Context mismatch');
                    intelligence.set(t.id,data);failed.delete(t.id);
                }catch(e){if(e.name!=='AbortError'&&current===generation)failed.add(t.id);}
            }));
            if(current!==generation)return;render();
        }
        grid.setAttribute('aria-busy','false');
    }
    async function load(){
        const current=++generation;controller?.abort();controller=new AbortController();intelligence.clear();failed.clear();
        reload.disabled=true;grid.setAttribute('aria-busy','true');grid.replaceChildren();status.textContent='Loading stored trend evidence...';
        try{
            const data=await read('/api/trends',{signal:controller.signal});const watches=await read('/api/watchlist',{signal:controller.signal});
            if(current!==generation)return;
            topics=data.trends;saved=new Set(watches.watchlist.map(t=>t.trend_id));render();
            await loadStates(savedOnly?topics.filter(t=>saved.has(t.id)):topics.filter(t=>t.data_mode==='real'),current,controller.signal);
        }catch(e){if(current===generation&&e.name!=='AbortError'){status.textContent='Unable to load stored evidence. Use Refresh evidence to retry.';grid.setAttribute('aria-busy','false');}}
        finally{if(current===generation)reload.disabled=false;}
    }
    document.querySelectorAll('[data-category]').forEach(button=>button.addEventListener('click',()=>{
        category=button.dataset.category;document.querySelectorAll('.category-tabs button').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));render();
    }));
    search.addEventListener('input',render);reload.addEventListener('click',load);
    document.querySelector('#reset-filters').addEventListener('click',()=>{category='';search.value='';document.querySelector('.category-tabs button').click();});
    load();
})();
