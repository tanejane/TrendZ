'use strict';
const $ = id => document.getElementById(id);
const labels = {profile:['supported','partially_supported','unsupported','insufficient_evidence'],affinity:['strong_affinity','moderate_affinity','weak_affinity','no_affinity','insufficient_evidence']};
const domains = ['beauty','fashion','lifestyle','health_wellness','other'];
const specs = ['skincare','makeup','haircare','fragrance','general_beauty'];
const state = {kind:'profile',summary:null,current:null,dirty:false,epoch:0};
const title = value => String(value).replaceAll('_',' ').replace(/\b\w/g, c => c.toUpperCase());
function node(tag, text, className) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(className)n.className=className; return n; }
function message(text, success=false) { $('message').textContent=text; $('message').className=success?'success':''; }
async function api(url, body) {
  const options=body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':document.querySelector('meta[name=review-token]').content},body:JSON.stringify(body)};
  const response=await fetch(url,options); const data=await response.json();
  if(!response.ok)throw new Error(data.message||data.reason||'Request failed');
  return data;
}
function choices(container, values, checked=[]) {
  $(container).replaceChildren();
  for(const value of values) { const label=node('label'); const input=document.createElement('input'); input.type='checkbox'; input.value=value; input.checked=checked.includes(value); label.append(input,document.createTextNode(' '+title(value))); $(container).append(label); }
}
function checked(container) { return [...$(container).querySelectorAll('input:checked')].map(n=>n.value); }
function filtered() {
  if(!state.summary)return [];
  const search=$('search').value.trim().toLowerCase();
  return state.summary.units.filter(u=>u.unit_type===state.kind && (!$('group').value||u.readiness_group===$('group').value) &&
    (!$('topic').value||u.topic_id===$('topic').value) && (!$('status').value||Boolean(u.human_label)===($('status').value==='reviewed')) &&
    (!search||(u.display_name+' '+u.creator_id).toLowerCase().includes(search)));
}
function renderQueue() {
  const rows=filtered(); $('queue').replaceChildren(); $('queue-count').textContent=rows.length+' fixed rows';
  for(const row of rows) {
    const button=node('button',row.display_name); button.type='button'; button.dataset.unitId=row.unit_id;
    button.setAttribute('aria-current',String(state.current?.fixed.unit_id===row.unit_id));
    button.append(node('small',(row.topic_id?title(row.topic_id)+' / ':'')+(row.human_label?title(row.human_label):'Pending')));
    button.addEventListener('click',()=>openUnit(row.unit_id)); $('queue').append(button);
  }
}
async function refresh() {
  state.summary=await api('/api/review');
  for(const kind of ['profile','affinity']) { const p=state.summary.by_type[kind]; $(kind+'-progress').textContent=p.reviewed+'/'+p.total; }
  $('session-state').textContent='Fixed source '+state.summary.session.source_sha256.slice(0,12)+' / Human labels only / Sample-scoped evidence';
  $('evaluate').disabled=!state.summary.ready; renderQueue();
}
function fact(key,value) { $('facts').append(node('dt',key),node('dd',value===null||value===undefined?'Unavailable':String(value))); }
function selectCount() {
  const ids=checked('videos'); const current=new Set(state.current?.fixed.videos.map(v=>v.video_id)||[]);
  $('selection-count').textContent=ids.filter(x=>current.has(x)).length+' sample / '+ids.filter(x=>!current.has(x)).length+' prior selected';
}
function renderVideos(fixed, review) {
  $('videos').replaceChildren();
  const evidence=new Map((fixed.affinity_proposal?.video_evidence||[]).map(e=>[e.video_id,e]));
  for(const video of [...fixed.videos,...(fixed.prior_videos||[])]) {
    const item=node('article',undefined,'video'); const top=node('div',undefined,'video-top');
    const checkbox=document.createElement('input'); checkbox.type='checkbox'; checkbox.value=video.video_id; checkbox.id='video-'+video.video_id; checkbox.checked=review.selected_video_ids.includes(video.video_id);
    checkbox.addEventListener('change',()=>{state.dirty=true;selectCount();});
    const label=node('label',video.title||'Prior reviewed seed: '+video.video_id); label.htmlFor=checkbox.id;
    top.append(checkbox,label);
    if(/^[A-Za-z0-9_-]{11}$/.test(video.video_id)) { const img=document.createElement('img'); img.src='https://i.ytimg.com/vi/'+video.video_id+'/mqdefault.jpg'; img.alt=''; img.loading='lazy'; img.addEventListener('error',()=>img.hidden=true); top.append(img); }
    item.append(top);
    const link=node('a','Open Video'); link.href='https://www.youtube.com/watch?v='+encodeURIComponent(video.video_id); link.target='_blank'; link.rel='noopener noreferrer'; item.append(link);
    item.append(node('p','Published '+video.published_at+' / Retrieved '+video.retrieved_at,'muted'));
    const match=evidence.get(video.video_id);
    const seed=fixed.seed_provenance.find(s=>s.video_id===video.video_id);
    item.append(node('p',video.sample_scope==='prior_seed_outside_sample'?'Prior seed / Outside current sample denominator':match?.existing_human_confirmed?'Inherited reviewed-relevant video':match?.proposed_topic_match?'Provisional vocabulary match':fixed.unit_type==='profile'&&seed?'Previously reviewed seed / '+title(seed.topic_id):'Sampled content / Not confirmed for this review','tag'));
    const details=document.createElement('details'); details.append(node('summary','Description and Source'));
    details.append(node('p',video.description||'Description unavailable in this fixed record.','description'));
    details.append(node('pre',JSON.stringify({source_ref:video.source_ref,views:video.views,likes:video.likes,comments:video.comments,topic_evidence:match||null},null,2)));
    item.append(details); $('videos').append(item);
  }
  selectCount();
}
function render(row) {
  state.current=row; const f=row.fixed,r=row.review;
  $('empty').hidden=true; $('content').hidden=false; $('creator-name').textContent=f.display_name;
  $('unit-kind').textContent=f.unit_type==='profile'?'Creator Profile':title(f.topic_id)+' / Topic Affinity';
  $('channel-link').href='https://www.youtube.com/channel/'+encodeURIComponent(f.channel_id); $('channel-link').textContent=f.channel_id;
  $('group-state').textContent=(f.readiness_group==='review_ready'?'Review-ready under draft gates':'Insufficient under draft gates')+' / Not a validated classification';
  $('facts').replaceChildren();
  fact('Proposed Domains',f.profile_proposal.proposed_domains.map(title).join(', ')||'Unavailable');
  fact('Proposed Specializations',f.profile_proposal.proposed_specializations.map(title).join(', ')||'Unavailable');
  const support=map=>Object.entries(map||{}).filter(([,ids])=>ids.length).map(([name,ids])=>title(name)+': '+ids.length).join(' / ')||'No text-screen support';
  fact('Domain Text Evidence',support(f.profile_proposal.domain_evidence));fact('Specialization Text Evidence',support(f.profile_proposal.specialization_evidence));
  fact('Sampled Videos',f.videos.length);fact('Sample Span',f.profile_proposal.sample_span.span_days?.toFixed(2)+' days');fact('Evidence Cutoff',f.as_of);
  if(f.unit_type==='affinity') {
    const a=f.affinity_proposal; fact('Affinity State',a.state+' / No categorical prediction');fact('Confirmed in Sample',a.confirmed_sample_relevant_count);
    fact('Screened Relevant',a.proposed_relevant_count);fact('Screened Coverage',a.coverage);fact('Screened Sample Share',a.proposed_topic_share===null?'Unavailable':(a.proposed_topic_share*100).toFixed(1)+'%');
    fact('Screened Span',a.proposed_publication_history.span_days);fact('Days Since Coverage',a.days_since_latest_proposed?.toFixed(2));
    fact('Screened Active Weeks',a.proposed_publication_history.active_publication_weeks);
  }
  $('warnings').replaceChildren();for(const warning of [...(f.profile_proposal.quality_warnings||[]),...(f.affinity_proposal?.quality_warnings||[])])$('warnings').append(node('li',warning));
  $('engagement').textContent=JSON.stringify(f.engagement,null,2);$('market').textContent=JSON.stringify(f.market_evidence,null,2);
  $('provenance').textContent=JSON.stringify({unit_id:f.unit_id,method:f.method_version,collection:f.collection,seed_provenance:f.seed_provenance,profile_evidence:f.profile_proposal,topic_evidence:f.affinity_proposal||null},null,2);
  $('human-label').replaceChildren(new Option('Not Reviewed',''),...labels[f.unit_type].map(value=>new Option(title(value),value)));
  $('human-label').value=r.human_label||'';
  choices('domains',domains,r.human_domains);choices('specializations',specs,r.human_specializations);
  $('classification-fields').hidden=f.unit_type!=='profile';$('use-topic').hidden=f.unit_type!=='affinity';
  $('sufficiency').value=r.evidence_sufficiency||''; $('explanation').value=r.explanation_support||''; $('basis').value=r.review_basis||'';
  $('notes').value=r.notes; $('reviewer').value=r.reviewer||localStorage.getItem('creator-reviewer')||'';
  $('revision').textContent='Revision '+r.revision+(r.saved_at?' / '+r.saved_at:' / Pending');
  $('history').open=false;$('history-content').replaceChildren();
  renderVideos(f,r);state.dirty=false;renderQueue();
}
async function openUnit(id) {
  if(state.dirty&&!confirm('Leave unsaved review changes?'))return;
  const epoch=++state.epoch;$('workspace').setAttribute('aria-busy','true');
  for(const input of document.querySelectorAll('#review-form input,#review-form select,#review-form textarea,#review-form button,#videos input'))input.disabled=true;
  try { const row=await api('/api/review/unit?unit_id='+encodeURIComponent(id));if(epoch===state.epoch)render(row); }
  catch(error) { if(epoch===state.epoch){state.current=null;$('content').hidden=true;$('empty').hidden=false;$('empty').textContent='Review unavailable. Select a row to retry.';message(error.message);} }
  finally { if(epoch===state.epoch){$('workspace').setAttribute('aria-busy','false');for(const input of document.querySelectorAll('#review-form input,#review-form select,#review-form textarea,#review-form button,#videos input'))input.disabled=false;} }
}
async function changeFilter() {
  renderQueue();const rows=filtered();
  if(rows.length&&!rows.some(r=>r.unit_id===state.current?.fixed.unit_id))await openUnit(rows[0].unit_id);
  if(!rows.length) { if(state.dirty&&!confirm('Leave unsaved review changes?'))return;state.current=null;state.dirty=false;$('content').hidden=true;$('empty').hidden=false;$('empty').textContent='No rows match these filters.'; }
}
async function navigate(offset) { const rows=filtered();const i=rows.findIndex(r=>r.unit_id===state.current?.fixed.unit_id); if(rows[i+offset])await openUnit(rows[i+offset].unit_id); }
function payload() { return {unit_id:state.current.fixed.unit_id,revision:state.current.review.revision,human_label:$('human-label').value,
  human_domains:state.kind==='profile'?checked('domains'):[],human_specializations:state.kind==='profile'?checked('specializations'):[],
  selected_video_ids:checked('videos'),evidence_sufficiency:$('sufficiency').value,explanation_support:$('explanation').value,
  review_basis:$('basis').value,notes:$('notes').value,reviewer:$('reviewer').value}; }
$('review-form').addEventListener('input',()=>state.dirty=true);
$('review-form').addEventListener('submit',async event=>{
  event.preventDefault();if(!state.current)return;const id=state.current.fixed.unit_id;const rows=filtered();const next=rows[rows.findIndex(r=>r.unit_id===id)+1]?.unit_id;
  const advance=event.submitter?.id==='save-next';$('save').disabled=true;$('save-next').disabled=true;
  try { const data=await api('/api/review/save',payload());localStorage.setItem('creator-reviewer',$('reviewer').value);state.current.review=data.saved;state.dirty=false;
    await refresh();await openUnit(advance&&next?next:id);message('Review saved. Revision '+data.saved.revision,true);
  } catch(error) {message(error.message);}finally {$('save').disabled=false;$('save-next').disabled=false;}
});
$('use-profile').addEventListener('click',()=>{
  const f=state.current.fixed.profile_proposal;choices('domains',domains,f.proposed_domains);choices('specializations',specs,f.proposed_specializations);
  const ids=new Set([...f.proposed_domains.flatMap(x=>f.domain_evidence[x]||[]),...f.proposed_specializations.flatMap(x=>f.specialization_evidence[x]||[])]);
  for(const checkbox of $('videos').querySelectorAll('input'))checkbox.checked=ids.has(checkbox.value);
  $('basis').value='assisted_review';state.dirty=true;selectCount();
});
$('use-topic').addEventListener('click',()=>{const ids=new Set(state.current.fixed.affinity_proposal.video_evidence.filter(v=>v.proposed_topic_match||v.existing_human_confirmed).map(v=>v.video_id));
  for(const checkbox of $('videos').querySelectorAll('input'))checkbox.checked=ids.has(checkbox.value);$('basis').value='assisted_review';state.dirty=true;selectCount();});
$('reset').addEventListener('click',async()=>{if(!state.current||!confirm('Return this review to pending? Previous revisions will remain.'))return;
  try {await api('/api/review/save',{unit_id:state.current.fixed.unit_id,revision:state.current.review.revision,reviewer:$('reviewer').value,notes:$('notes').value,reset:true});state.dirty=false;await refresh();await openUnit(state.current.fixed.unit_id);message('Returned to pending; history preserved.',true);}catch(error){message(error.message);}});
$('history').addEventListener('toggle',async()=>{if(!$('history').open||!state.current)return;const id=state.current.fixed.unit_id;
  try {const data=await api('/api/review/history?unit_id='+encodeURIComponent(id));if(state.current?.fixed.unit_id!==id)return;$('history-content').replaceChildren();
    if(!data.events.length)$('history-content').append(node('p','No saved revisions.','muted'));
    for(const event of data.events)$('history-content').append(node('pre',JSON.stringify(event,null,2)));}catch(error){message(error.message);}});
for(const id of ['group','status','topic'])$(id).addEventListener('change',changeFilter);$('search').addEventListener('input',changeFilter);
for(const tab of document.querySelectorAll('[role=tab]'))tab.addEventListener('click',async()=>{
  if(state.dirty&&!confirm('Leave unsaved review changes?'))return;state.dirty=false;state.kind=tab.dataset.kind;state.current=null;
  for(const t of document.querySelectorAll('[role=tab]'))t.setAttribute('aria-selected',String(t===tab));$('topic').value='';$('topic').disabled=state.kind==='profile';$('export').href='/api/review/export/'+state.kind;await changeFilter();
});
$('previous').addEventListener('click',()=>navigate(-1));$('next').addEventListener('click',()=>navigate(1));
$('evaluate').addEventListener('click',async()=>{try {const data=await api('/api/review/evaluate',{});$('evaluation-json').textContent=JSON.stringify(data,null,2);$('evaluation-output').hidden=false;message('Evaluation saved for this review revision.',true);}catch(error){message(error.message);}});
window.addEventListener('beforeunload',event=>{if(state.dirty){event.preventDefault();event.returnValue='';}});
(async()=>{try{await refresh();const topics=[...new Set(state.summary.units.map(r=>r.topic_id).filter(Boolean))].sort();for(const t of topics)$('topic').append(new Option(title(t),t));$('topic').disabled=true;await changeFilter();}catch(error){message(error.message);}})();
