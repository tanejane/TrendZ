"""Bounded uploads-playlist collection for an explicitly supplied seed channel."""

import os
import re
from datetime import datetime, timezone
from .youtube import request_json


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class CreatorYouTube:
    def __init__(self, key=None, transport=request_json, clock=utc_now):
        self.key = key or os.environ.get('YOUTUBE_API_KEY')
        if not self.key:
            raise ValueError('YOUTUBE_API_KEY is required for live creator collection')
        self.transport, self.clock = transport, clock

    def collect(self, channel_id, max_videos=20, scan_limit=50):
        if not channel_id or not 1 <= max_videos <= scan_limit <= 50:
            raise ValueError('Require a channel ID and 1 <= max_videos <= scan_limit <= 50')
        started = self.clock()
        payload = {'channel_id':channel_id, 'retrieved_at':started, 'data_mode':'real',
                   'policy':{'max_videos':max_videos,'scan_limit':scan_limit,
                             'method':'recent_public_within_first_uploads_page_v1'},
                   'requests':[], 'selected_ids':[], 'excluded':[], 'state':'unavailable',
                   'reason':None, 'region_code':None}

        def request(resource, params):
            event = {'resource':resource,'params':params,'started_at':self.clock()}
            payload['requests'].append(event)
            try:
                response = self.transport(resource, {'key':self.key, **params})
                if not isinstance(response, dict) or not isinstance(response.get('items'), list):
                    raise ValueError('Invalid response shape')
                event.update(retrieved_at=self.clock(), response=response)
                return response
            except Exception as error:
                # Neither exception URLs nor credential-bearing params belong in an archive.
                event.update(retrieved_at=self.clock(),error='Request failed: '+type(error).__name__)
                status = re.search(r'YouTube HTTP ([0-9]{3})',str(error))
                if status:
                    event['http_status'] = int(status.group(1))
                raise RuntimeError(event['error']) from None

        try:
            channels = request('channels', {'part':'snippet,contentDetails','id':channel_id})
            channel = next((c for c in channels['items'] if c.get('id')==channel_id),None)
            if not channel:
                raise RuntimeError('Seed channel unavailable')
            playlist = channel.get('contentDetails',{}).get('relatedPlaylists',{}).get('uploads')
            if not playlist:
                raise RuntimeError('Uploads playlist unavailable')
            page = request('playlistItems', {'part':'snippet,contentDetails','playlistId':playlist,
                                              'maxResults':scan_limit})
            ids = list(dict.fromkeys(item.get('contentDetails',{}).get('videoId') or
                       item.get('snippet',{}).get('resourceId',{}).get('videoId')
                       for item in page['items'][:scan_limit]))
            ids = [identifier for identifier in ids if identifier]
            payload['playlist_has_more'] = bool(page.get('nextPageToken'))
            payload['scanned_video_ids'] = ids
            if not ids:
                payload.update(state='available',reason='No public video identifiers in bounded playlist sample')
                return payload
            details = request('videos', {'part':'snippet,statistics,status','id':','.join(ids)})
            videos = {v.get('id'):v for v in details['items'] if v.get('id') in ids}
            valid = []
            for identifier in ids:
                video = videos.get(identifier)
                snippet = (video or {}).get('snippet',{})
                reason = None
                if video is None:
                    reason = 'Video absent from public details response'
                elif snippet.get('channelId') != channel_id:
                    reason = 'Channel identity mismatch'
                elif video.get('status',{}).get('privacyStatus') != 'public':
                    reason = 'Public visibility not established'
                else:
                    try:
                        published = datetime.fromisoformat(snippet['publishedAt'].replace('Z','+00:00'))
                        stamp = datetime.fromisoformat(payload['requests'][-1]['retrieved_at'].replace('Z','+00:00'))
                        if published.tzinfo is None or published > stamp:
                            raise ValueError('Invalid publication time')
                    except (ValueError,KeyError,TypeError):
                        reason = 'Invalid or future publication timestamp'
                if reason:
                    payload['excluded'].append({'video_id':identifier,'reason':reason})
                else:
                    valid.append(video)
            valid.sort(key=lambda v:(datetime.fromisoformat(v['snippet']['publishedAt'].replace('Z','+00:00')),v['id']),reverse=True)
            payload['selected_ids'] = [v['id'] for v in valid[:max_videos]]
            payload.update(state='partial' if payload['excluded'] else 'available',
                           reason='Some scanned videos were excluded' if payload['excluded'] else None)
        except RuntimeError as error:
            # Only our sanitized request or fixed validation messages are propagated.
            payload['reason'] = str(error)
        except (ValueError,KeyError,TypeError,AttributeError):
            payload['reason'] = 'Malformed API metadata; raw response retained for inspection'
        return payload


def normalize_capture(payload, run_id):
    """Derive report values with exact raw response references, not a raw-data copy."""
    channel_id = payload['channel_id']
    selected = set(payload.get('selected_ids',[]))
    rows = []
    for request_index,event in enumerate(payload.get('requests',[])):
        if event['resource'] != 'videos':
            continue
        for item_index,video in enumerate(event.get('response',{}).get('items',[])):
            snippet = video.get('snippet',{})
            if video.get('id') not in selected or snippet.get('channelId')!=channel_id:
                continue
            def counter(name):
                value = video.get('statistics',{}).get(name)
                try:
                    return int(value) if value is not None and int(value)>=0 else None
                except (ValueError,TypeError,OverflowError):
                    return None
            rows.append({'video_id':video['id'],'channel_id':channel_id,
                'title':snippet.get('title',''),'description':snippet.get('description',''),
                'published_at':snippet['publishedAt'],'retrieved_at':event['retrieved_at'],
                'views':counter('viewCount'),'likes':counter('likeCount'),'comments':counter('commentCount'),
                'source_ref':{'run_id':run_id,'request_index':request_index,'item_index':item_index},
                'sample_scope':'bounded_uploads','source_query_id':None,
                'url':'https://www.youtube.com/watch?v='+video['id'],
                'statistics_scope':'retrieval_time_not_historical'})
    return rows
