"""Source-specific descriptive components; never combine interest and video units."""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from .metrics import calculate_series, measured, unavailable
from .pilot_report import validate_series

METRICS = ('recent_growth','acceleration','persistence','volatility')


def search_components(observations):
    groups = defaultdict(list)
    for row in observations:
        if row['source'] == 'google_trends' and row['metric'] == 'interest_score':
            groups[(row['series_id'],row['source_identifier'])].append(row)
    if not groups:
        return [], {key:unavailable('No measured Google interest series') for key in METRICS}, [], []
    rows = max(groups.values(),key=lambda group:max(r['retrieved_at'] for r in group))
    request = rows[0]['metadata'].get('request',{})
    timeframe = request.get('timeframe','').split()
    reasons = []
    try:
        first,last = [date.fromisoformat(value) for value in timeframe]
        expected = [(first+timedelta(days=i)).isoformat() for i in range((last-first).days+1)]
        if not expected:
            raise ValueError('Reversed window')
        reasons = validate_series(rows,'google_trends',expected)['reasons']
        if any(not 0 <= r['value'] <= 100 for r in rows):
            reasons.append('Interest value outside 0-100')
        if any(r['observation_date'] not in expected for r in rows):
            reasons.append('Observation outside request window')
    except (ValueError,TypeError):
        reasons = ['Invalid or missing fixed Google timeframe']
    warnings = ['Search interest is query-relative, not absolute demand or purchase intent',
                'Google query intent has not been manually validated; YouTube audit cannot validate it']
    # A transparent quality heuristic, not a confidence probability or lifecycle rule.
    zero_fraction = sum(r['value']==0 for r in rows)/len(rows)
    if zero_fraction > 0.5:
        warnings.append('Sparse search series: more than half of stored days are zero-valued')
    values = {key:unavailable('; '.join(reasons)) for key in METRICS} if reasons else calculate_series(rows)
    return rows,values,reasons,warnings


def publication_components(run):
    empty = {key:unavailable('No immutable publication discovery run') for key in METRICS}
    if run is None:
        return empty, ['No immutable publication discovery run'], {}, []
    windows = run['capture'].get('windows',[])
    if not windows:
        return empty,['No publication windows in selected run'],{},[]
    reasons = []
    counts, dates, videos = {}, [], {}
    for window in windows:
        if window.get('capped') or not window.get('complete') or window.get('error'):
            reasons.append('Capped or failed discovery windows; content growth is unavailable')
        try:
            start,stop = date.fromisoformat(window['start']),date.fromisoformat(window['end_exclusive'])
            if stop <= start:
                raise ValueError('Reversed publication window')
            request = window.get('request',{})
            if (request.get('q')!=run['capture']['query'] or request.get('regionCode')!=run['capture']['market'] or
                    request.get('publishedAfter')!=start.isoformat()+'T00:00:00Z' or
                    request.get('publishedBefore')!=stop.isoformat()+'T00:00:00Z'):
                reasons.append('Publication request/query/market/window provenance mismatch')
            window_days = [(start+timedelta(days=i)).isoformat() for i in range((stop-start).days)]
            if set(window_days)&set(dates):
                reasons.append('Overlapping publication windows')
            dates.extend(window_days)
            for day in window_days:
                counts.setdefault(day,set())
            for response in window.get('responses',[]):
                for item in response.get('items',[]):
                    identifier = item.get('id',{}).get('videoId')
                    snippet = item.get('snippet',{})
                    if not identifier or not snippet.get('publishedAt'):
                        reasons.append('Search result lacks video ID or publication timestamp')
                        continue
                    published = datetime.fromisoformat(snippet['publishedAt'].replace('Z','+00:00')).astimezone(timezone.utc).date()
                    if start <= published < stop:
                        counts[published.isoformat()].add(identifier)
                        videos[identifier] = {'id':identifier,**snippet}
        except (ValueError,KeyError,TypeError):
            reasons.append('Invalid publication-window provenance')
    reasons = sorted(set(reasons))
    components = {key:unavailable('; '.join(reasons)) for key in METRICS} if reasons else (
        calculate_series([{'observation_date':day,'value':len(ids)} for day,ids in counts.items()]) if counts else empty)
    summary = {'discovered_videos':len(videos),'window_count':len(windows),
               'complete_windows':sum(bool(w.get('complete')) and not w.get('capped') and not w.get('error') for w in windows),
               'capped_windows':sum(bool(w.get('capped')) for w in windows),
               'failed_windows':sum(bool(w.get('error')) for w in windows)}
    return components,reasons,summary,list(videos.values())


def creator_components(videos):
    unique = {v['id']:v for v in videos}
    channels = Counter(v.get('channelId') for v in unique.values() if v.get('channelId'))
    missing = len(unique)-sum(channels.values())
    total = sum(channels.values())
    return {'sample_video_count':len(unique),'sample_channel_count':len(channels),
            'missing_channel_count':missing,'share_denominator_known_channel_videos':total,
            'largest_channel_share':measured(max(channels.values())/total,'fraction') if total else unavailable('No channel IDs'),
            'channel_hhi':measured(sum((n/total)**2 for n in channels.values()),'concentration') if total else unavailable('No channel IDs')}


def velocity_components(cohort,snapshots):
    members = {r['video_id']:r for r in cohort['members']}
    groups = defaultdict(dict)
    for row in snapshots:
        if row['cohort_id'] == cohort['cohort_id'] and row['video_id'] in members:
            groups[(row['snapshot_date'],row['run_id'])][row['video_id']] = row
    latest_by_date = {}
    for (day,run_id),rows in groups.items():
        stamp = max(r['retrieved_at'] for r in rows.values())
        if day not in latest_by_date or stamp > latest_by_date[day][0]:
            latest_by_date[day] = (stamp,run_id,rows)
    days = sorted(latest_by_date)
    if len(days)<2:
        return {'views_per_hour':unavailable('Requires two distinct snapshot dates for the same fixed cohort'),
                'likes_per_hour':unavailable('Requires two distinct snapshot dates for the same fixed cohort')},[],[],[]
    before,after = [latest_by_date[day][2] for day in days[-2:]]
    rates = {'views':[],'likes':[]}
    reasons = []
    for identifier,member in members.items():
        a,b = before.get(identifier),after.get(identifier)
        if not a or not b:
            reasons.append('Missing paired cohort members')
            continue
        if a['status']=='unavailable' or b['status']=='unavailable':
            reasons.append('Unavailable video snapshot in pair')
            continue
        try:
            first = datetime.fromisoformat(a['retrieved_at'].replace('Z','+00:00'))
            last = datetime.fromisoformat(b['retrieved_at'].replace('Z','+00:00'))
            selected_at = datetime.fromisoformat(cohort['selected_at'].replace('Z','+00:00'))
            if first.tzinfo is None or last.tzinfo is None:
                raise ValueError('Naive timestamps')
            hours = (last-first).total_seconds()/3600
            if selected_at.tzinfo is None or first<selected_at or hours<=0 or (
                    first.astimezone(timezone.utc).date().isoformat()!=a['snapshot_date'] or
                    last.astimezone(timezone.utc).date().isoformat()!=b['snapshot_date'] or
                    a['published_at']!=member['published_at'] or b['published_at']!=member['published_at']):
                raise ValueError('Invalid pair provenance')
        except ValueError:
            reasons.append('Invalid snapshot timestamp or publication provenance')
            continue
        for field in rates:
            if a[field] is None or b[field] is None:
                reasons.append('Missing '+field+' counters')
            elif min(a[field],b[field])<0 or b[field]<a[field]:
                reasons.append('Negative/corrected '+field+' delta; not treated as velocity')
            else:
                rates[field].append((b[field]-a[field])/hours)
    components = {field+'_per_hour':measured(sum(values),'matched_sample_'+field+'_per_hour') if values else unavailable(
        'No valid paired '+field+' counters') for field,values in rates.items()}
    components.update({'fixed_cohort_size':len(members),'paired_view_videos':len(rates['views']),
                       'paired_like_videos':len(rates['likes'])})
    return components,sorted(set(reasons)),[latest_by_date[d][1] for d in days[-2:]],days[-2:]
