"""Evidence-depth reporting, deliberately without Creator Fit ranking."""

import json
from collections import Counter


def summarize(creators):
    topics = sorted({topic for creator in creators for topic in creator['topics']})
    return {'creator_count':len(creators),'sample_video_records':sum(len(c['videos']) for c in creators),
        'unique_video_ids':len({v['video_id'] for c in creators for v in c['videos']}),
        'live_expanded_creators':sum(c['collection']['scope']=='bounded_uploads' and c['collection']['state'] in ('available','partial') for c in creators),
        'unavailable_collections':sum(c['collection']['state']=='unavailable' for c in creators),
        'profile_review_ready':sum(c['profile']['evidence_ready_for_profile_review'] for c in creators),
        'profile_insufficient':sum(not c['profile']['evidence_ready_for_profile_review'] for c in creators),
        'human_validated_profile_count':0,
        'creators_with_median_views':sum(c['engagement']['views']['median'] is not None for c in creators),
        'creators_with_median_likes':sum(c['engagement']['likes']['median'] is not None for c in creators),
        'creators_with_valid_like_view_ratio':sum(c['engagement']['like_view_ratio']['median_of_video_ratios'] is not None for c in creators),
        'creators_with_multiple_screened_topics':sum(sum(t['proposed_relevant_count']>0 for t in c['topics'].values())>=2 for c in creators),
        'market_states':dict(Counter(c['market_evidence']['state'] for c in creators)),
        'by_topic':{topic:{
            'creators_with_confirmed_sample_video':sum(c['topics'][topic]['confirmed_sample_relevant_count']>0 for c in creators),
            'creators_with_proposed_topic_videos':sum(c['topics'][topic]['proposed_relevant_count']>0 for c in creators),
            'creators_with_repeated_screened_coverage':sum(c['topics'][topic]['coverage']=='repeated_screened' for c in creators),
            'creators_with_repeated_confirmed_coverage':sum(c['topics'][topic]['confirmed_sample_relevant_count']>=2 and c['topics'][topic]['confirmed_publication_history']['distinct_publication_dates']>=2 for c in creators),
            'draft_moderate_screen_gate':sum(c['topics'][topic]['draft_threshold_sensitivity']['draft_moderate_gate']['screen_assisted_meets_gate'] for c in creators),
            'draft_strong_screen_gate':sum(c['topics'][topic]['draft_threshold_sensitivity']['draft_strong_gate']['screen_assisted_meets_gate'] for c in creators)
        } for topic in topics}}


def markdown(creators, summary, status):
    lines = ['# Phase 5B Creator Evidence Expansion', '',
        '**Evidence expansion and review preparation only. No Creator Fit ranking, score, UI or gold labels.**', '',
        status, '',
        'Selection: only channels referenced by the eight existing canonical size-5 relevant-video cohorts. Live policy: up to 20 public videos selected by publication date from at most the first 50 uploads-playlist entries per channel. This is bounded, not an upload census; unavailable videos are not zero-filled.', '',
        '## Evidence Depth', '',
        '| Measure | Count |','| --- | ---: |']
    for key,value in summary.items():
        if not isinstance(value,dict):
            lines.append(f'| {key} | {value} |')
    lines += ['', 'Profile review readiness uses the Phase 5A draft 3-video/14-day/2-week gate and repeated text evidence. It is not a validated specialization. All new classifications and topic matches remain provisional; final human fields are blank.', '',
        '## Videos Per Creator', '',
        '| Channel ID | Creator | Scanned / details / selected | Collection scope | Profile review ready | Screened specializations | Views / likes / ratio available |',
        '| --- | --- | --- | --- | --- | --- | --- |']
    for c in creators:
        engagement=c['engagement']
        label=c['display_name'].replace('|','/').replace('\n',' ')
        flags=['yes' if value is not None else 'no' for value in (engagement['views']['median'],engagement['likes']['median'],engagement['like_view_ratio']['median_of_video_ratios'])]
        depth=f"{c['collection'].get('scanned_video_count','not collected')} / {c['collection'].get('details_returned_count','reused')} / {len(c['videos'])}"
        lines.append(f"| {c['channel_id']} | {label} | {depth} | {c['collection']['scope']} | {c['profile']['evidence_ready_for_profile_review']} | {', '.join(c['profile']['proposed_specializations']) or 'insufficient'} | {' / '.join(flags)} |")
    lines += ['', 'The ID-ordered table is an inventory, not a ranking. Creator-specific run IDs, exact source paths, titles, descriptions, publication/retrieval dates and all counters are in review_dataset.json.', '',
        '## Topic History and Draft Sensitivity', '',
        '| Topic | Confirmed sample coverage: creators | Proposed coverage: creators | Repeated screened | Repeated human-confirmed | Draft moderate gate | Draft strong gate |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for topic,data in summary['by_topic'].items():
        lines.append('| '+topic+' | '+' | '.join(str(v) for v in data.values())+' |')
    lines += ['',
        'Sensitivity columns compare the unvalidated Phase 5A gates (2 videos/7 days/2 weeks versus 3 videos/28 days/3 weeks) on screened evidence only. They do not enact strong/moderate labels. The report keeps confirmed counts separate, since screening agreement is not independent human validation.', '',
        'Topic overlap is count of creators with text-screen matches for multiple pilot topics, not established multiple specializations. Aliases and supporting-only proxies retain matched terms, fields and cautions. Retinal/retinoids are not silently treated as retinol; generic oils/hydration and festival-only mentions do not automatically count as the core topics.', '',
        '## Engagement', '',
        'Views, likes and comments are public counters at their recorded retrieval times, never historical engagement. Median is the sample median; variability is population standard deviation only with >=2 observed values. Like/view ratio is the median of per-video ratios with nonmissing likes and views>0, not ratio of medians. Missing counts stay null. Video ages and formats are not normalized; popularity is not topical suitability. No engagement velocity is produced from this expansion.', '',
        '## Market Evidence', '',
        'A first-party channel country declaration, when returned, is partial evidence only, not verified residence or audience geography. No automatic market state is verified. Existing MY regionCode applies only to seed-search viewability; uploads collection does not apply an MY filter. Audience geography and Malaysian-market content remain unknown without direct reviewed evidence.', '',
        '## Review Workflow', '',
        'Open review_dataset.json and inspect each creator\'s videos, proposed profile, evidence counts, example video IDs and eight topic evidence bundles. Human profile/topic labels are blank; inherited human seed evidence is preserved in separate provenance fields. Review new matches and profile assertions rather than accepting text hits as gold. This phase exports a fixed review dataset but does not import or finalize new human labels.', '',
        '## API / Data Limitations', '',
        '- Only 40 pre-existing cohort channels are eligible; deleted/private/mismatched videos are excluded with reasons. No unrestricted influencer discovery or search calls.',
        '- Sampling is first uploads page only; the most recent selection is within that bounded page. Playlist reordering, missing details or hidden videos can leave fewer than the requested 20.',
        '- Current live collection uses at most three requests per creator (channels, playlistItems, videos), up to 120 requests for 40 creators. No unbounded retries. Completed per-channel captures resume without requests; explicit retries remain new immutable runs.',
        '- Vocabulary screening cannot validate video/audio meaning, multilingual content, boilerplate descriptions, negation, product use, sponsorship, credentials or stable creator identity. Unmatched text is not a negative gold label.',
        '- Query-selected legacy evidence, when used without live access, is not recent creator-content expansion and has no meaningful whole-sample topic share.',
        '- Counter availability and sample selection are separate; missing statistics do not prove zero engagement.',
        '- Product Fit v1 rules, catalogue, labels, predictions, rankings and reports are unchanged. No campaign/ROI, lifecycle, recommendation or AI changes.', '',
        '## Official Collection References', '',
        '- [channels.list](https://developers.google.com/youtube/data/reference/rest/v3/channels/list): uploads-playlist discovery and optional declared channel metadata.',
        '- [playlistItems.list](https://developers.google.com/youtube/data/reference/rest/v3/playlistItems/list): bounded uploads entries, maximum 50 per request.',
        '- [videos.list](https://developers.google.com/youtube/data/reference/rest/v3/videos/list): current video details/status/counters.', '',
        'Phase 5B stops at evidence expansion. Review the evidence depth and provisional matches before Phase 5C.']
    return '\n'.join(lines)+'\n'


def export(directory, creators, status, manifest):
    directory.mkdir(parents=True,exist_ok=True)
    summary = summarize(creators)
    artifacts = {'metrics.json':json.dumps({'status':status,**summary,'manifest':manifest},indent=2,ensure_ascii=True)+'\n',
                 'review_dataset.json':json.dumps({'status':status,'independent_gold':False,'manifest':manifest,'creators':creators},indent=2,ensure_ascii=True)+'\n',
                 'report.md':markdown(creators,summary,status)}
    for name,content in artifacts.items():
        target=directory/name
        if target.exists() and target.read_text(encoding='utf-8')!=content:
            raise ValueError('Refusing to overwrite a different review artifact; select a new --output directory')
    for name,content in artifacts.items():
        (directory/name).write_text(content,encoding='utf-8')
    return summary
