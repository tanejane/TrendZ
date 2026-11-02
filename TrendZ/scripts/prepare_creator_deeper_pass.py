"""Part B report/drafts only: no save calls and no final evaluation."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.creator_review import fingerprint
from services.creator_review_assists import prepare_pack
from scripts.prepare_creator_assists import read_session, protected_hashes
from scripts.phase5c_deeper_decisions import deeper_changes


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def supplemental(root, fixed, db):
    path = root/'reports/phase5b/live-initial/raw'/(fixed['collection']['run_id']+'.json')
    raw = json.loads(path.read_text(encoding='utf-8')); payload = json.loads(raw['payload'])
    if hashlib.sha256(raw['payload'].encode()).hexdigest() != raw['sha256']:
        raise ValueError('Immutable raw payload hash mismatch')
    request = payload['requests'][0]
    channel = next(c for c in request['response']['items'] if c['id'] == fixed['channel_id'])
    result = {'channel_profile': {'channel_id': channel['id'],
        'description': channel['snippet'].get('description'),
        'title': channel['snippet'].get('title'),
        'source_ref': {'run_id': raw['run_id'], 'request_index': 0},
        'retrieved_at': request['retrieved_at'], 'raw_file': str(path.relative_to(root)),
        'raw_file_sha256': digest(path), 'raw_payload_sha256': raw['sha256'],
        'scope': 'archived self-description, corroboration only; not verified credentials or audience'},
        'seed_discoveries': []}
    for seed in fixed['seed_provenance']:
        if fixed['unit_type'] == 'affinity' and seed['topic_id'] != fixed['topic_id']:
            continue
        rows = db.execute('SELECT * FROM youtube_discoveries WHERE run_id=? AND topic_id=? AND query_id=? AND video_id=?',
            (seed['run_id'], seed['topic_id'], seed['query_id'], seed['video_id'])).fetchall()
        for row in rows:
            data = dict(row); search = json.loads(data.pop('payload')); snippet = search['snippet']
            if snippet['channelId'] != fixed['channel_id']:
                raise ValueError('Seed channel identity mismatch')
            result['seed_discoveries'].append({**data, 'title': snippet.get('title'),
                'description': snippet.get('description'), 'channel_id': snippet['channelId'],
                'raw_search_payload_sha256': fingerprint(search), 'prior_review': seed,
                'scope': 'original discovery snippet; may be truncated; never backfilled into fixed unit'})
    return result


def revise(session, records, original):
    changes = deeper_changes(records)
    pending_ids = {r['unit_id'] for r in original['rows'] if r['confidence'] != 'high'}
    if set(changes) != pending_ids or len(changes) != 56:
        raise ValueError('Deeper pass must cover exactly the original 56 non-high units')
    decisions = []
    for d in original['rows']:
        copy = {k: d[k] for k in ('unit_id', 'proposed_label', 'selected_video_ids', 'confidence',
            'evidence_sufficiency', 'explanation_support', 'explanation_reason', 'reason', 'manual_question')}
        copy.update({k: d[k] for k in ('proposed_domains', 'proposed_specializations', 'proxy_video_ids') if k in d})
        if d['unit_id'] in changes:
            copy.update(changes[d['unit_id']])
            label = copy['proposed_label']
            copy['evidence_sufficiency'] = ('insufficient' if label == 'insufficient_evidence'
                else 'partial' if label in ('weak_affinity', 'partially_supported') else 'sufficient')
            # These original screen explanations do not substantiate their apparent
            # repeated/core-topic inference. The original proposals remain immutable.
            if (d['unit_type'] == 'affinity' and
                (label == 'insufficient_evidence' or set(d['selected_video_ids']) - set(copy['selected_video_ids']))):
                copy['explanation_support'] = ('unsupported' if d['topic_id'] == 'glass-skin' or
                    d['display_name'] == 'Dr Nicole J' and d['topic_id'] == 'retinol' else 'insufficient_evidence')
                copy['explanation_reason'] = 'Original mention-based coverage is not substantive verification. ' + copy['reason']
            if d['display_name'] in ('CNBC-TV18', 'Kitsch') and d['unit_type'] == 'affinity':
                copy['explanation_support'] = 'supported'
                copy['explanation_reason'] = 'Original seed identity and explicit topical wording are recoverable in immutable discovery provenance, without altering the fixed snapshot.'
        decisions.append(copy)
    validated = prepare_pack(session, records, {'source_sha256': session['source_sha256'], 'rows': decisions})
    revised = []
    for d in validated['rows']:
        if d['unit_id'] not in changes:
            continue
        initial = next(x for x in original['rows'] if x['unit_id'] == d['unit_id'])
        d.update(original_confidence=initial['confidence'], original_suggested_label=initial['proposed_label'],
            upgraded_to_high=d['confidence'] == 'high', application_state='not_applied_part_b',
            assist_source='deeper_frozen_metadata_seed_and_archived_profile_inspection',
            underlying_evidence_limitations=d['unresolved_uncertainty'])
        revised.append(d)
    return revised


def report(rows, access, progress):
    counts = {kind: dict(Counter(r['confidence'] for r in rows if r['unit_type'] == kind))
              for kind in ('profile', 'affinity')}
    lines = ['# Phase 5C: Assisted Application and Deeper Evidence Pass', '',
        'Part A: 48 high-confidence suggestions saved with assisted_review provenance, not independent human gold.',
        'Part B: all 56 rows below remain unsaved. No final evaluation generated.', '',
        '## Progress', '', '| Review unit | Saved | Remaining |', '| --- | ---: | ---: |']
    for kind, c in progress['by_type'].items():
        lines.append(f"| {kind} | {c['reviewed']} | {c['total']-c['reviewed']} |")
    lines += ['', '## Deeper Draft Confidence', '', '| Unit | Upgraded to high | Medium | Low |', '| --- | ---: | ---: | ---: |']
    for kind, c in counts.items():
        lines.append(f"| {kind} | {c.get('high',0)} | {c.get('medium',0)} | {c.get('low',0)} |")
    lines += ['', 'High confidence means a defensible scoped disposition, often WEAKER than the initial draft. It does not mean strong affinity or a new approval.',
        'Every row still has evidence limitations; medium/low rows need deeper human inspection. No underlying ambiguity is hidden by a high-confidence weak/qualified label.', '',
        '## Public Access Limits', '', access['summary'],
        'Channel self-descriptions were instead read from existing immutable Phase 5B channel responses. Original discovery snippets were read with strict run/topic/query/video identity. No source records were changed.', '',
        '## Important Corrections', '',
        '- Dhivya Sri: Diwali shorts promote the same exact tutorial/lookup link; propose weak, not repeated affinity.',
        '- Yuvaap: full monsoon description explicitly covers scalp massage; propose one weak scalp-care example despite the alias screen missing it.',
        '- Valentina glass-skin: no inherited human-approved seed exists for this pair. The initial assistance rationale claiming one was wrong; hydration/glow plus hashtags remain insufficient.',
        '- Dr Nicole J retinol: the product called Retinol Serum is described as containing retinal; exclude that product-name hit from repeated retinol evidence.',
        '- SiPalingSkincare: archived About explicitly says brand-content reposting; do not attribute original skills/authorship.',
        '- Rania: archived About explicitly says permanent makeup. Keep profile separate from the unresolved ordinary lip-tint versus permanent lip-coloring decision.',
        '- CNBC-TV18 and Kitsch: recover original seed titles/snippets from immutable discoveries, outside current-sample denominators.', '',
        '## Remaining Genuinely Manual Units', '', '| Creator | Unit/topic | Confidence | Exact unresolved reason |', '| --- | --- | --- | --- |']
    def cell(value): return str(value).replace('|', '\\|').replace('\n',' ')
    for r in rows:
        if r['confidence'] != 'high':
            lines.append('| '+' | '.join(cell(v) for v in (r['display_name'], r['topic_id'] or 'profile', r['confidence'], r['unresolved_uncertainty']))+' |')
    lines += ['', '## All 56 Revised Drafts']
    for r in rows:
        lines += ['', '### '+r['display_name']+(' / '+r['topic_id'] if r['topic_id'] else ' / profile'),
            '', '`'+r['unit_id']+'`', '',
            f"Initial: `{r['original_suggested_label']}` ({r['original_confidence']}). Proposed now: **{r['proposed_label']}** ({r['confidence']}).",
            'Finding: '+r['reason'], 'Limits / unresolved evidence: '+r['unresolved_uncertainty'],
            'Sufficiency: `'+r['evidence_sufficiency']+'`. Explanation-support draft: `'+r['explanation_support']+'`. '+r['explanation_reason']]
        if r['unit_type'] == 'profile':
            lines.append('Proposed domains: '+', '.join(r['proposed_domains'])+'; specializations: '+', '.join(r['proposed_specializations'])+'.')
        for v in r['selected_evidence']:
            lines.append('- Candidate support ['+v['video_id']+'](https://www.youtube.com/watch?v='+v['video_id']+'): '+(v['title'] or '[outside-sample seed; see supplemental discovery]'))
        if r['proxy_video_ids']:
            lines.append('Excluded proxy/context IDs: '+', '.join('`'+x+'`' for x in r['proxy_video_ids']))
        lines += ['Original group: `'+r['readiness_group']+'`. `review_basis=assisted_review`. **NOT APPLIED**.']
    return '\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/phase5c/deeper-pass-v1')
    args = parser.parse_args()
    if args.output.exists(): raise ValueError('Use a new output directory')
    review = ROOT/'data/creators/review_sessions/local.sqlite3'
    before = protected_hashes(ROOT, review)
    session, records, counts = read_session(review)
    original_path = ROOT/'reports/phase5c/assists/preparation-v1/review_assists.json'
    original = json.loads(original_path.read_text(encoding='utf-8'))
    rows = revise(session, records, original)
    fixed = {r['fixed']['unit_id']:r['fixed'] for r in records}
    measured = ROOT/'reports/phase2-measured/pilot.sqlite3'
    db = sqlite3.connect(measured.resolve().as_uri()+'?mode=ro', uri=True); db.row_factory=sqlite3.Row
    try:
        evidence = {r['unit_id']: supplemental(ROOT, fixed[r['unit_id']], db) for r in rows}
    finally: db.close()
    # The listed primary pages were actually attempted with the web tool in this
    # session. The sole returned About document contained only YouTube footer links.
    video_ids = sorted({(r['selected_video_ids']+r.get('proxy_video_ids',[]))[0]
                        for r in original['rows'] if r['confidence'] != 'high'} | {'9anp6SS6-Lo'})
    channels = sorted(r['creator_id'].split(':',1)[1] for r in rows if r['unit_type']=='profile')
    access = {'attempted_at_utc_date': datetime.now(timezone.utc).date().isoformat(),
        'tool': 'web open/search', 'usable_new_page_evidence': 0,
        'video_pages': [{'url':'https://www.youtube.com/watch?v='+v, 'status':'failed_to_fetch_cache_miss'} for v in video_ids],
        'channel_about_pages': [{'url':'https://www.youtube.com/channel/'+c+'/about',
            'status':'footer_only_no_profile_evidence' if c=='UC4SCRUgnsl6HmWyJ6n1zLJA' else 'failed_to_fetch_cache_miss'} for c in channels],
        'targeted_searches': ['site:youtube.com/watch "Rania Refat" "Lip tint"',
            'site:youtube.com "Маришка" "99000181161"', 'site:youtube.com "Dhivya Sri" "diwali"',
            'site:youtube.com "Brooke Rush Reviews" scalp'], 'search_result':'no results',
        'summary':'47 unique video pages failed with cache misses. Of 18 channel About pages, 17 failed and one returned only a footer. Four targeted searches returned no results. No playback, transcript or usable new public-profile evidence was obtained.'}
    after = protected_hashes(ROOT, review)
    if before != after: raise ValueError('Protected data changed during read-only deeper preparation')
    per_kind = {kind:dict(Counter(r['confidence'] for r in rows if r['unit_type']==kind)) for kind in ('profile','affinity')}
    summary = {'session_id':session['session_id'], 'source_sha256':session['source_sha256'],
        'original_assist_sha256':digest(original_path), 'deeper_rows':56, 'part_b_labels_written':0,
        'upgraded_to_high':sum(r['confidence']=='high' for r in rows),
        'remaining_manual':sum(r['confidence']!='high' for r in rows), 'confidence_by_type':per_kind,
        'part_b_units_not_applied':[r['unit_id'] for r in rows],
        'genuinely_manual_units':[r['unit_id'] for r in rows if r['confidence']!='high'],
        'review_basis':'assisted_review', 'independent_human_gold':False,
        'protected_evidence_and_review_db_unchanged':True, 'review_table_counts':counts,
        'evaluation_generated':False, 'protected_sha256':before}
    # Summary only: never call the review evaluator/finalizer.
    progress={'by_type':{kind:{'total':sum(r['fixed']['unit_type']==kind for r in records),
        'reviewed':sum(r['fixed']['unit_type']==kind and r['review']['human_label'] is not None for r in records)} for kind in ('profile','affinity')}}
    args.output.mkdir(parents=True)
    def write(name,value):
        with (args.output/name).open('x',encoding='utf-8') as f:
            f.write(value if isinstance(value,str) else json.dumps(value,indent=2,ensure_ascii=True)+'\n')
    write('revised_suggestions.json',{'summary':summary,'rows':rows})
    write('supplemental_evidence.json',{'measured_database_sha256':digest(measured),'units':evidence})
    write('public_access_log.json',access)
    write('summary.json',summary)
    write('REVIEW_REPORT.md',report(rows,access,progress))
    print(json.dumps({k:summary[k] for k in ('deeper_rows','upgraded_to_high','remaining_manual','confidence_by_type','part_b_labels_written','evaluation_generated')}))


if __name__=='__main__': main()
