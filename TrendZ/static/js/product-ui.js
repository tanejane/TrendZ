/* Presentation coordination only: source services own every evidence/gating result. */
(() => {
    const contexts=new WeakMap();
    const node=(tag,text,parent,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;parent?.append(e);return e;};
    function icons(){window.feather?.replace();}
    function progress(step){
        document.querySelectorAll('.planner-progress').forEach(list=>{
            list.dataset.plannerStep=step;
            list.querySelectorAll('[data-step]').forEach(item=>{
                const current=Number(item.dataset.step);
                item.dataset.progress=current<step?'complete':current===step?'current':'upcoming';
                if(current===step)item.setAttribute('aria-current','step');else item.removeAttribute('aria-current');
            });
        });
    }
    document.querySelectorAll('.planner-progress').forEach(list=>progress(Number(list.dataset.plannerStep)));
    function preview(root){
        const target=root.querySelector('.selected-product');if(!target)return;
        const selected=contexts.get(root)?.products.find(p=>p.product_id===root.querySelector('[name=product_id]').value);
        target.replaceChildren();target.hidden=!selected;
        if(!selected)return;
        const symbol=node('div',null,target,'selected-product-symbol');symbol.setAttribute('aria-hidden','true');
        const mark=node('i',null,symbol);mark.dataset.feather='package';
        const copy=node('div',null,target);node('p','Selected product context',copy,'product-eyebrow');node('h3',selected.product_name,copy);
        const badge=node('span',selected.fit_state.replaceAll('_',' '),copy,'evidence-badge');badge.dataset.fitState=selected.fit_state;
        node('p',selected.category+' · Source-backed compatibility, not measured efficacy.',copy);
        icons();
    }
    document.addEventListener('trendz:products-ready',event=>{
        const root=event.target;contexts.set(root,event.detail);preview(root);
    });
    document.addEventListener('change',event=>{
        const root=event.target.closest('.tz-creator-controls')?.closest('.tz-creators');
        if(root){preview(root);progress(2);}
    });
    document.addEventListener('trendz:candidates-ready',()=>progress(3));
    document.addEventListener('trendz:scenario-context',event=>{
        const target=document.querySelector('#scenario-selection');if(!target)return;
        target.replaceChildren();const e=event.detail.evidence;
        const fit=e.product_fit.fit_state.replaceAll('_',' ')+(e.product_fit.fit_state==='supporting_fit'?' (indirect compatibility)':'');
        const fields={'Trend':e.trend.topic_id.replaceAll('-',' '),'Product':e.product_fit.product_name+' / '+fit,
            'Creator':e.creator_candidate.creator_name,'Candidate state':e.creator_candidate.candidate_state.replaceAll('_',' ')};
        for(const [label,value]of Object.entries(fields)){const group=node('div',null,target);node('span',label,group);node('strong',value,group);}
        progress(event.detail.scenario_eligible?4:3);
    });
    const outcomes=document.querySelector('#scenario-outcomes');
    if(outcomes){
        let calculated=false;
        new MutationObserver(()=>{
            const ready=!!outcomes.querySelector('dl');progress(ready?5:4);
            if(ready&&!calculated)document.querySelector('#outcomes-title')?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth',block:'start'});
            calculated=ready;
        }).observe(outcomes,{childList:true,subtree:true});
    }
    const save=document.querySelector('[data-save-topic]');
    if(save){
        let saved=false;const topic=save.dataset.saveTopic;const status=document.querySelector('#detail-save-status');
        function label(){save.setAttribute('aria-pressed',String(saved));save.querySelector('span').textContent=saved?'Saved to watchlist':'Save trend';}
        fetch('/api/watchlist').then(r=>r.json()).then(data=>{saved=data.watchlist.some(t=>t.trend_id===topic);label();}).catch(()=>{status.textContent='Watchlist status could not be loaded.';});
        save.addEventListener('click',async()=>{
            save.disabled=true;
            try{
                const r=await fetch('/api/watchlist/'+(saved?'remove':'add'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({trend_id:topic})});
                if(!r.ok)throw new Error();saved=!saved;label();status.textContent=saved?'Trend saved.':'Trend removed from watchlist.';
            }catch(_){status.textContent='Watchlist update failed. Please retry.';}
            finally{save.disabled=false;}
        });
    }
    if(document.querySelector('.planner-topic'))fetch('/api/trends').then(r=>r.json()).then(data=>{
        document.querySelectorAll('.planner-topic').forEach(link=>{const topic=data.trends.find(t=>t.id===link.dataset.topic);if(topic)link.dataset.category=topic.category;});
    }).catch(()=>{});
    icons();
})();
