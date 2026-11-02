"""One completed UTC publication day plus separately dated fixed-cohort counters."""

import hashlib
from datetime import date, datetime, timedelta, timezone

from .youtube import YouTube
from ..youtube_store import encoded


class YouTubeDaily(YouTube):
    def collect_day(self, topics, cohorts, publication_day, audit_id):
        day = date.fromisoformat(publication_day)
        stamp = self.clock()
        snapshot_day = datetime.fromisoformat(stamp.replace('Z', '+00:00')).astimezone(timezone.utc).date()
        if day >= snapshot_day:
            raise ValueError('Publication day must be a completed UTC day')
        stop = day + timedelta(days=1)
        captures, snapshots = [], []
        requests = {'search':0,'videos':0}
        outcomes = []
        for topic in topics:
            params = {'part':'snippet','type':'video','q':topic['query'],'regionCode':topic['market'],
                      'order':'date','maxResults':50,'publishedAfter':day.isoformat()+'T00:00:00Z',
                      'publishedBefore':stop.isoformat()+'T00:00:00Z'}
            response, error = None, None
            try:
                requests['search'] += 1
                response = self.transport('search', {'key':self.key,**params})
            except Exception as failure:
                error = str(failure)
            outcomes.append({'endpoint':'search','topic_id':topic['id'],'completed':response is not None})
            videos = {}
            for item in (response or {}).get('items', []):
                snippet, video_id = item.get('snippet',{}), item.get('id',{}).get('videoId')
                published = snippet.get('publishedAt')
                if video_id and published:
                    published_day = datetime.fromisoformat(published.replace('Z','+00:00')).astimezone(timezone.utc).date()
                    if day <= published_day < stop:
                        videos[video_id] = {'id':video_id,**snippet}
            capped = bool((response or {}).get('nextPageToken'))
            window = {'start':day.isoformat(),'end_exclusive':stop.isoformat(),
                      'responses':[response] if response is not None else [],'request':params,
                      'complete':response is not None and not capped,'capped':capped,'error':error,
                      'discovered_video_count':len(videos) if response is not None else None}
            captures.append({'topic_id':topic['id'],'query_id':'canonical','query':topic['query'],
                             'market':topic['market'],'retrieved_at':self.clock(),'windows':[window],
                             'videos':list(videos.values()),'data_mode':'real' if response is not None else 'unavailable',
                             'signal':'content_supply','publication_date':day.isoformat()})
        topic_ids = {topic['id'] for topic in topics}
        topic_by_id = {topic['id']:topic for topic in topics}
        for cohort in cohorts:
            if cohort['topic_id'] not in topic_ids or cohort['query_id'] != 'canonical':
                continue
            members = cohort['members']
            if not members:
                continue
            stats, error = {}, None
            try:
                requests['videos'] += 1
                payload = self.transport('videos', {'key':self.key,'part':'snippet,statistics',
                                                   'id':','.join(member['video_id'] for member in members)})
                stats = {item['id']:item for item in payload.get('items', [])}
            except Exception as failure:
                error = str(failure)
            outcomes.append({'endpoint':'videos','topic_id':cohort['topic_id'],'completed':error is None})
            counter_stamp = self.clock()
            counter_day = datetime.fromisoformat(counter_stamp.replace('Z','+00:00')).astimezone(timezone.utc).date()
            for member in members:
                video = stats.get(member['video_id'])
                counters = (video or {}).get('statistics',{})
                views, likes = counters.get('viewCount'), counters.get('likeCount')
                reasons = [error] if error else ['Video absent from API response'] if video is None else []
                if views is None:
                    reasons.append('View count unavailable')
                if likes is None:
                    reasons.append('Like count unavailable')
                snapshots.append({'cohort_id':cohort['cohort_id'],'topic_id':cohort['topic_id'],
                                  'query_id':'canonical','video_id':member['video_id'],
                                  'query':topic_by_id[cohort['topic_id']]['query'],
                                  'market':topic_by_id[cohort['topic_id']]['market'],
                                  'source':'youtube','source_url':'https://www.youtube.com/watch?v='+member['video_id'],
                                  'published_at':member['published_at'],'snapshot_date':counter_day.isoformat(),
                                  'retrieved_at':counter_stamp,'views':int(views) if views is not None else None,
                                  'likes':int(likes) if likes is not None else None,
                                  'status':'unavailable' if video is None else 'partial' if reasons else 'available',
                                  'reason':'; '.join(reasons) or None,'raw_response':video,
                                  'statistic_time':'retrieval_time_not_publication_time'})
        return {'retrieved_at':self.clock(),'publication_day':day.isoformat(),'collection_started_at':stamp,
                'audit_id':audit_id,'captures':captures,'snapshots':snapshots,'requests':requests,
                'request_outcomes':outcomes,
                'data_mode':'real' if any(c['data_mode']=='real' for c in captures) else 'unavailable',
                'request_fingerprint':hashlib.sha256(encoded({'topics':topics,'cohorts':cohorts,
                                                             'publication_day':publication_day}).encode()).hexdigest()}
