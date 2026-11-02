"""Six independent descriptive dimensions, with explicit scopes and evidence gates."""

from datetime import date, timedelta
from .topics import query_variants
from .metrics import unavailable
from .intelligence_evidence import read_evidence
from .intelligence_components import search_components, publication_components, creator_components, velocity_components

VERSION = 'intelligence-dimensions-v1'


def window(dates):
    return {'start':min(dates) if dates else None,'end':max(dates) if dates else None}


class IntelligenceService:
    def __init__(self, database_path, topics):
        self.path, self.topics = database_path, topics

    def topic(self, topic_id, query_id='canonical'):
        topic = next((t for t in self.topics if t['id']==topic_id),None)
        if topic is None:
            raise KeyError('Topic not found')
        variants = query_variants(topic)
        query = next((q for q in variants if q['query_id']==query_id),None)
        if query is None:
            raise ValueError('Unknown query_id for this topic')
        evidence = read_evidence(self.path,topic,query)
        observations = evidence['observations']
        runs = evidence['runs']
        selected = max(runs,key=lambda r:(r['capture']['retrieved_at'],r['run_id'])) if runs else None
        audit = [r for r in evidence['audit'] if selected and r['run_id']==selected['run_id']]
        google,search,search_errors,search_warnings = search_components(observations)
        publication,pub_errors,pub_summary,videos = publication_components(selected)
        pub_dates = []
        if selected:
            for w in selected['capture'].get('windows',[]):
                try:
                    start,end = date.fromisoformat(w['start']),date.fromisoformat(w['end_exclusive'])
                    pub_dates.extend((start+timedelta(days=i)).isoformat() for i in range((end-start).days))
                except (ValueError,KeyError):
                    pass
        google_dates = [r['observation_date'] for r in google]
        google_ids = {'observation_ids':[r['id'] for r in google],
                      'series_ids':sorted({r['series_id'] for r in google})}
        pub_ids = {'run_ids':[selected['run_id']] if selected else [],
                   'run_sha256':{selected['run_id']:selected['sha256']} if selected else {}}
        dimensions = {}

        def dimension(name,state,components,sources,dates,identifiers,scope,reasons=(),warnings=(),stamps=()):
            if not stamps:
                stamps = [r['capture']['retrieved_at'] for r in runs if r['run_id'] in identifiers.get('run_ids',[])]
                stamps += [r['retrieved_at'] for r in evidence['snapshots'] if r['run_id'] in identifiers.get('run_ids',[])]
                stamps += [r['retrieved_at'] for r in google if r['id'] in identifiers.get('observation_ids',[])]
            dimensions[name] = {'state':state,'components':components,'source':sources,
                                'query_id':query_id,'query':query['query'],'market':topic['market'],
                                'observation_window':window(dates),'method_version':VERSION+'/'+name,
                                'evidence_identifiers':identifiers,'scope':scope,
                                'unavailable_reasons':list(dict.fromkeys(reasons)) if state=='unavailable' else [],
                                'provisional_reasons':list(dict.fromkeys(reasons)) if state=='provisional' else [],
                                'quality_warnings':list(dict.fromkeys(warnings)),
                                'retrieval_window':window(list(stamps))}

        growth_ok = search['recent_growth']['state']=='available'
        sparse = any(w.startswith('Sparse search series') for w in search_warnings)
        search_state = ('provisional' if sparse else 'available') if growth_ok else 'unavailable'
        dimension('demand_momentum',search_state,
                  {k:search[k] for k in ('recent_growth','acceleration')},['google_trends'],google_dates,google_ids,
                  'within_query_relative_search_interest',
                  [search['recent_growth'].get('reason')] if not growth_ok else
                  ['Sparse normalized history limits interpretation'] if sparse else [],search_warnings,
                  [r['retrieved_at'] for r in google])

        search_p = search['persistence']['state']=='available'
        pub_p = publication['persistence']['state']=='available'
        persistence_state = ('provisional' if (sparse or not search_p) else 'available') if search_p or pub_p else 'unavailable'
        persistence_reasons = (['Sparse search history'] if search_p and sparse else []) + (
            ['Publication persistence is an unvalidated query-supply proxy'] if pub_p and not search_p else [])
        if not search_p and not pub_p:
            persistence_reasons = [search['persistence']['reason'],publication['persistence']['reason']]
        dimension('signal_persistence',persistence_state,
                  {'search':{k:search[k] for k in ('persistence','volatility')},
                   'publication':{k:publication[k] for k in ('persistence','volatility')}},
                  ['google_trends','youtube'],google_dates+pub_dates,{**google_ids,**pub_ids},
                  'separate_source_elevation_not_long_term_longevity',persistence_reasons,
                  search_warnings+pub_errors+['Search and publication units remain separate; no cross-source persistence score'])

        supply_ok = publication['recent_growth']['state']=='available'
        dimension('content_saturation','provisional' if supply_ok else 'unavailable',
                  {'saturation_level':unavailable('No defensible saturation benchmark'),
                   'supply_recent_growth':publication['recent_growth'],
                   'supply_acceleration':publication['acceleration'],'discovery_sample':pub_summary},
                  ['youtube'],pub_dates,pub_ids,'publication_supply_proxy_not_market_saturation',
                  ['No saturation benchmark; query relevance remains unvalidated'] if supply_ok else
                  [publication['recent_growth'].get('reason','No usable supply growth')],
                  pub_errors+['Currently discoverable sample is not an upload census',
                              'MY regionCode does not establish creator or audience nationality'])

        # Completed labels permit a relevant audited SAMPLE, never population diversity.
        decided = [r for r in audit if r['label']!='pending']
        relevant_ids = {r['video_id'] for r in audit if r['label']=='relevant'}
        reviewed = bool(audit) and len(decided)==len(audit)
        audited_videos = [v for v in videos if v['id'] in relevant_ids]
        sample = audited_videos if decided else videos
        creator = creator_components(sample)
        invalid_provenance = [r for r in pub_errors if 'provenance' in r or 'Overlapping' in r]
        enough = creator['sample_channel_count']>=2 and not invalid_provenance
        creator_state = ('available' if reviewed and not creator['missing_channel_count'] else 'provisional') if enough else 'unavailable'
        if not enough:
            creator_reasons = invalid_provenance or ['Fewer than two identified channels in the selected sample']
        else:
            creator_reasons = ['Human relevance audit incomplete or deferred'] if not reviewed else []
        if enough and creator['missing_channel_count']:
            creator_reasons.append('Some sampled videos lack channel IDs')
        dimension('creator_diversity',creator_state,creator,['youtube'],pub_dates,
                  {**pub_ids,'video_ids':sorted(v['id'] for v in sample),
                   'audit_candidate_ids':[r['candidate_id'] for r in audit]},
                  'audited_relevant_sample' if decided else 'unreviewed_query_sample',creator_reasons,
                  ['Channel concentration describes this sample only, never population-level creator diversity']+pub_errors)

        cohort = evidence['cohorts'][-1] if evidence['cohorts'] else None
        if cohort:
            velocity,velocity_reasons,snapshot_runs,snapshot_days = velocity_components(cohort,evidence['snapshots'])
            views_ok = velocity['views_per_hour']['state']=='available'
            likes_ok = velocity['likes_per_hour']['state']=='available'
            state = ('provisional' if velocity_reasons or not likes_ok else 'available') if views_ok else 'unavailable'
            if not views_ok:
                velocity_reasons = velocity_reasons+[velocity['views_per_hour']['reason']]
            dimension('engagement_velocity',state,velocity,['youtube'],snapshot_days,
                      {'run_ids':snapshot_runs,'cohort_ids':[cohort['cohort_id']],
                       'video_ids':sorted(r['video_id'] for r in cohort['members']),
                       'audit_candidate_ids':[r['candidate_id'] for r in cohort['members']]},
                      'matched_fixed_cohort_counter_deltas',velocity_reasons,
                      ['Retrieval-time counter changes, never historical views reconstructed from publication dates',
                       'Video age, format and small-cohort selection limit generalization'])
        else:
            dimension('engagement_velocity','unavailable',
                      {'views_per_hour':unavailable('No human-relevant fixed cohort'),
                       'likes_per_hour':unavailable('No human-relevant fixed cohort')},['youtube'],[],{},
                      'matched_fixed_cohort_counter_deltas',['No relevant fixed cohort with repeated snapshots'],
                      ['Legacy discovery-cohort totals cannot substitute for fixed-cohort snapshots'])

        zero_count = sum(r['value']==0 for r in google)
        google_expected = None
        missing_days = None
        if google:
            try:
                first,last = [date.fromisoformat(s) for s in google[0]['metadata']['request']['timeframe'].split()]
                expected = {(first+timedelta(days=i)).isoformat() for i in range((last-first).days+1)}
                google_expected,missing_days = len(expected),len(expected-set(google_dates))
            except (KeyError,ValueError):
                pass
        confidence = {'google_observed_days':len(set(google_dates)),'google_expected_days':google_expected,
                      'google_missing_days':missing_days,'google_zero_days':zero_count,
                      'google_series_validation_reasons':search_errors,'youtube_discovery':pub_summary,
                      'audit_candidates_for_selected_run':len(audit),'audit_labelled':len(decided),
                      'audit_pending':len(audit)-len(decided),'audit_status':'deferred_or_pending' if not reviewed else 'reviewed_sample',
                      'fixed_cohorts':len(evidence['cohorts']),'snapshot_records':len(evidence['snapshots']),
                      'google_intent_validation':'unavailable',
                      'reproducibility':'selected_surviving_runs_only' if selected and selected['kind']=='legacy' else 'immutable_runs' if runs else 'observations_only'}
        has_evidence = bool(observations or runs or evidence['snapshots'])
        dimension('data_confidence','available' if has_evidence else 'unavailable',confidence,
                  sorted({r['source'] for r in observations}|({'youtube'} if runs else set())),
                  google_dates+pub_dates,{**google_ids,**pub_ids,'audit_candidate_ids':[r['candidate_id'] for r in audit]},
                  'evidence_quality_diagnostics_not_confidence_probability',[] if has_evidence else ['No measured evidence'],
                  ['Diagnostic availability is not validated intelligence',
                   'Relevance audit remains deferred or incomplete' if not reviewed else 'Relevance evidence covers only the audited sample']+
                  (['Earlier overwritten legacy captures cannot be recovered'] if selected and selected['kind']=='legacy' else []))
        return {'topic_id':topic_id,'query_id':query_id,'query':query['query'],'market':topic['market'],
                'available_queries':[{'query_id':q['query_id'],'query':q['query']} for q in variants],
                'data_mode':'real' if observations or any(r['capture'].get('data_mode')=='real' for r in runs)
                or evidence['snapshots'] else 'unavailable','method_version':VERSION,'dimensions':dimensions}
