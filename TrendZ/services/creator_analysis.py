"""Explainable text-screen evidence and descriptive counters, never creator rankings."""

import html
import re
import statistics
import unicodedata
from datetime import datetime, timezone

METHOD = 'creator-evidence-expansion-v1'


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timezone-aware timestamps required')
    return parsed.astimezone(timezone.utc)


def text(value):
    return re.sub(r'[-_\s]+',' ',unicodedata.normalize('NFKC',html.unescape(value or '')).casefold())


def hits(video, terms):
    result = []
    for field in ('title','description'):
        content = text(video.get(field))
        for term in terms:
            if re.search(r'(?<!\w)'+re.escape(text(term))+r'(?!\w)',content):
                result.append({'term':term,'field':field})
    return result


def span(videos):
    dates = sorted(timestamp(v['published_at']) for v in videos)
    return {'first_published_at':dates[0].isoformat() if dates else None,
            'latest_published_at':dates[-1].isoformat() if dates else None,
            'span_days':(dates[-1]-dates[0]).total_seconds()/86400 if dates else None,
            'active_publication_weeks':len({d.isocalendar()[:2] for d in dates}),
            'distinct_publication_dates':len({d.date() for d in dates})}


def counters(videos):
    values = {field:[v[field] for v in videos if v.get(field) is not None] for field in ('views','likes','comments')}
    result = {'state':'available' if values['views'] else 'unavailable',
              'scope':'sampled_video_counters_at_retrieval_not_historical_or_channel_totals',
              'video_count':len(videos), 'velocity':{'state':'unavailable','reason':'This expansion does not collect repeated fixed-cohort snapshot pairs'},
              'retrieval_timestamps':sorted({v['retrieved_at'] for v in videos})}
    for field, series in values.items():
        result[field] = {'available':len(series),'missing':len(videos)-len(series),
                         'median':statistics.median(series) if series else None,
                         'population_stddev':statistics.pstdev(series) if len(series)>=2 else None,
                         'min':min(series) if series else None, 'max':max(series) if series else None}
    ratios = [v['likes']/v['views'] for v in videos if v.get('likes') is not None and v.get('views') is not None and v['views']>0]
    result['like_view_ratio'] = {'median_of_video_ratios':statistics.median(ratios) if ratios else None,
                                'valid_denominators':len(ratios),'missing_or_zero_denominators':len(videos)-len(ratios)}
    result['quality_warnings'] = ['Video age/format are not normalized; popularity is not topical fit']
    if len(values['views'])<len(videos) or len(values['likes'])<len(videos):
        result['state'] = 'provisional' if values['views'] else 'unavailable'
        result['quality_warnings'].append('Missing counters remain null, not zero')
    return result


def analyze_creator(seed, videos, vocabulary, as_of, collection, channel_metadata=None):
    cutoff = timestamp(as_of)
    valid, exclusions = {}, []
    for video in sorted(videos,key=lambda v:(v['retrieved_at'],v['source_ref']['run_id'])):
        try:
            if video['channel_id']!=seed['channel_id'] or timestamp(video['published_at'])>cutoff or timestamp(video['retrieved_at'])>cutoff:
                raise ValueError('Identity or cutoff mismatch')
        except (ValueError,TypeError,KeyError):
            exclusions.append(video.get('video_id'))
            continue
        valid[video['video_id']] = video
    videos = sorted(valid.values(),key=lambda v:(timestamp(v['published_at']),v['video_id']),reverse=True)
    profile_span = span(videos)
    specialization = {name:[v['video_id'] for v in videos if hits(v,terms)]
                      for name,terms in vocabulary['specializations'].items()}
    domains = {name:[v['video_id'] for v in videos if hits(v,terms)] for name,terms in vocabulary['domains'].items()}
    domains['beauty'] = sorted(set(domains['beauty'])|{identifier for ids in specialization.values() for identifier in ids})
    ready = len(videos)>=3 and (profile_span['span_days'] or 0)>=14 and profile_span['active_publication_weeks']>=2
    proposed_specs = [name for name,ids in specialization.items() if len(ids)>=2] if ready else []
    proposed_domains = [name for name,ids in domains.items() if len(ids)>=2] if ready else []
    profile = {'state':'provisional' if videos else 'unavailable','human_domain':None,'human_specializations':[],
               'as_of':cutoff.isoformat(),'vocabulary_version':vocabulary['version'],
               'evidence_references':[{'video_id':v['video_id'],'source_ref':v['source_ref'],
                                       'retrieved_at':v['retrieved_at']} for v in videos],
               'proposal_basis':'repeated_text_screen_not_human_validation',
               'evidence_ready_for_profile_review':bool(ready and (proposed_domains or proposed_specs)),
               'proposed_domains':proposed_domains,'proposed_specializations':proposed_specs,
               'domain_evidence':domains,'specialization_evidence':specialization,
               'sample_span':profile_span,
               'draft_gate':{'videos':3,'span_days':14,'weeks':2,'specialization_video_hits':2},
               'quality_warnings':['Text mentions, copied descriptions, hashtags and promotional links can overmatch',
                                   'No stable creator classification is finalized; general_beauty/other are not unknown defaults']}
    topics = {}
    bounded = collection['scope']=='bounded_uploads' and bool(videos) and all(v['sample_scope']=='bounded_uploads' for v in videos)
    for topic_id,terms in vocabulary['topics'].items():
        known = [s for s in seed['seeds'] if s['topic_id']==topic_id and timestamp(s['labelled_at'])<=cutoff]
        confirmed_ids = {s['video_id'] for s in known}
        evidence, proposed = [], []
        for video in videos:
            aliases, supporting = hits(video,terms['aliases']),hits(video,terms.get('supporting',[]))
            context = hits(video,terms.get('require_any',[]))
            eligible = bool(aliases) and (not terms.get('require_any') or bool(context))
            confirmed = video['video_id'] in confirmed_ids
            if eligible or confirmed:
                proposed.append(video)
            if aliases or supporting or confirmed:
                evidence.append({'video_id':video['video_id'],'source_ref':video['source_ref'],
                    'source_query_id':video['source_query_id'],'alias_hits':aliases,'supporting_hits':supporting,
                    'required_context_hits':context,'proposed_topic_match':eligible,
                    'existing_human_confirmed':confirmed,
                    'human_evidence':[s for s in known if s['video_id']==video['video_id']],
                    'human_label':None,'notes':''})
        confirmed = [v for v in videos if v['video_id'] in confirmed_ids]
        proposed_span, confirmed_span = span(proposed),span(confirmed)
        sensitivity = {}
        for name,n,days,weeks in [('draft_moderate_gate',2,7,2),('draft_strong_gate',3,28,3)]:
            sensitivity[name] = {'min_videos':n,'min_span_days':days,'min_weeks':weeks,
                'confirmed_only_meets_gate':len(confirmed)>=n and (confirmed_span['span_days'] or 0)>=days and confirmed_span['active_publication_weeks']>=weeks,
                'screen_assisted_meets_gate':len(proposed)>=n and (proposed_span['span_days'] or 0)>=days and proposed_span['active_publication_weeks']>=weeks}
        topics[topic_id] = {'state':'provisional' if proposed or known else 'unavailable','strength_state':None,
            'reason':'Draft thresholds not enacted; text screening needs human validation' if proposed or known else 'No confirmed or explicit screened topic evidence',
            'matching_version':vocabulary['version'],'query_id':'canonical',
            'query_scope':'content_screen_not_new_search_query','retrieval_market':None,
            'sample_video_count':len(videos),'confirmed_sample_relevant_count':len(confirmed),
            'prior_confirmed_video_ids':sorted(confirmed_ids),
            'prior_confirmed_outside_sample':sorted(confirmed_ids-set(valid)),
            'proposed_relevant_count':len(proposed),
            'proposed_topic_share':len(proposed)/len(videos) if bounded else None,
            'confirmed_relevance_lower_bound_share':len(confirmed)/len(videos) if bounded else None,
            'share_unavailable_reason':None if bounded else 'Query-selected legacy sample is not a bounded creator-content denominator',
            'proposed_publication_history':proposed_span,'confirmed_publication_history':confirmed_span,
            'days_since_latest_proposed':(cutoff-timestamp(proposed[0]['published_at'])).total_seconds()/86400 if proposed else None,
            'coverage':'repeated_screened' if len(proposed)>=2 and proposed_span['distinct_publication_dates']>=2 else 'one_off_screened' if proposed else 'unavailable',
            'draft_threshold_sensitivity':sensitivity,'video_evidence':evidence,
            'quality_warnings':[terms['caution'],'Unmatched text is not a verified negative; multilingual/audio/visual content is not fully assessed']}
    metadata_in_scope = not collection.get('channel_retrieved_at') or timestamp(collection['channel_retrieved_at'])<=cutoff
    country = (channel_metadata or {}).get('snippet',{}).get('country') if metadata_in_scope else None
    return {'creator_id':seed['creator_id'],'channel_id':seed['channel_id'],'display_name':seed['display_name'],
            'as_of':cutoff.isoformat(),'method_version':METHOD,'vocabulary_version':vocabulary['version'],
            'data_mode':'real' if videos else 'unavailable','collection':collection,
            'videos':videos,'excluded_video_ids':exclusions,'profile':profile,'topics':topics,
            'engagement':counters(videos),'seed_provenance':seed['seeds'],
            'market_evidence':{'state':'partial' if country else 'unknown','creator_country':
                {'state':'partial','value':country,'basis':'channel_self_declared_not_verified_residence',
                 'source_ref':collection.get('channel_source_ref'),'observed_at':collection.get('channel_retrieved_at')} if country else {'state':'unknown','value':None},
                'audience_geography':{'state':'unknown','value':None},'malaysian_content':{'state':'unknown'},
                'seed_retrieval_region':{'value':'MY','scope':'seed_search_viewability_only'},
                'expansion_region_code':None},
            'human_profile_label':None,'human_specializations':[],'review_notes':'',
            'review_status':'pending','independent_gold':False}
