"""Separate frozen creator review units and explicit human revisions; no producer writes."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .creator_analysis import timestamp

PROFILE_LABELS=('supported','partially_supported','unsupported','insufficient_evidence')
AFFINITY_LABELS=('strong_affinity','moderate_affinity','weak_affinity','no_affinity','insufficient_evidence')
DOMAINS=('beauty','fashion','lifestyle','health_wellness','other')
SPECIALIZATIONS=('skincare','makeup','haircare','fragrance','general_beauty')
SUFFICIENCY=('sufficient','partial','insufficient')
EXPLANATIONS=('supported','unsupported','insufficient_evidence')


def encoded(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


class CreatorReviewConflict(ValueError):
    pass


def build_units(snapshot):
    units=[]
    identities=set()
    for creator in sorted(snapshot['creators'],key=lambda c:c['creator_id']):
        identifier=creator['creator_id']
        if identifier in identities:
            raise ValueError('Duplicate creator identity')
        identities.add(identifier)
        group='review_ready' if creator['profile']['evidence_ready_for_profile_review'] else 'insufficient'
        base={'creator_id':identifier,'channel_id':creator['channel_id'],'display_name':creator['display_name'],
              'readiness_group':group,'as_of':creator['as_of'],'method_version':creator['method_version'],
              'profile_proposal':creator['profile'],'engagement':creator['engagement'],
              'market_evidence':creator['market_evidence'],'videos':creator['videos'],
              'seed_provenance':creator['seed_provenance'],'collection':creator['collection']}
        videos={v['video_id'] for v in base['videos']}
        if len(videos)!=len(base['videos']):
            raise ValueError('Duplicate sampled videos in fixed creator snapshot')
        units.append({**base,'unit_id':'profile/'+identifier,'unit_type':'profile','topic_id':None})
        for topic_id,affinity in sorted(creator['topics'].items()):
            if not affinity['proposed_relevant_count'] and not affinity['prior_confirmed_video_ids']:
                continue
            prior=[]
            for seed in creator['seed_provenance']:
                if seed['topic_id']==topic_id and seed['video_id'] not in videos:
                    prior.append({'video_id':seed['video_id'],'title':None,'description':None,
                        'published_at':seed['published_at'],'retrieved_at':seed['retrieved_at'],
                        'url':'https://www.youtube.com/watch?v='+seed['video_id'],
                        'source_ref':{'run_id':seed['run_id'],'candidate_id':seed['candidate_id'],
                                      'label_event_id':seed['label_event_id']},
                        'sample_scope':'prior_seed_outside_sample','views':None,'likes':None,'comments':None})
            units.append({**base,'unit_id':'affinity/'+identifier+'/'+topic_id,'unit_type':'affinity',
                          'topic_id':topic_id,'query_id':'canonical','affinity_proposal':affinity,
                          'prior_videos':prior,'selection_reason':'seed_or_explicit_screened_match'})
    return units


def blank_review():
    return {'human_label':None,'human_domains':[],'human_specializations':[],
            'selected_video_ids':[],'evidence_sufficiency':None,'explanation_support':None,
            'notes':'','reviewer':'','review_basis':None,'revision':0,'saved_at':None}


class CreatorReviewStore:
    def __init__(self,path):
        self.path=Path(path)

    @contextmanager
    def connect(self,create=False):
        db=sqlite3.connect(self.path.resolve().as_uri()+('?mode=rwc' if create else '?mode=rw'),timeout=15,uri=True)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def initialize(self,source):
        source=Path(source)
        raw=source.read_bytes()
        snapshot=json.loads(raw)
        units=build_units(snapshot)
        source_hash=hashlib.sha256(raw).hexdigest()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect(create=True) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS units (unit_id TEXT PRIMARY KEY,unit_type TEXT NOT NULL,
                    creator_id TEXT NOT NULL,topic_id TEXT,readiness_group TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews (unit_id TEXT PRIMARY KEY REFERENCES units(unit_id),
                    revision INTEGER NOT NULL,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (event_id INTEGER PRIMARY KEY,unit_id TEXT NOT NULL REFERENCES units(unit_id),
                    before_json TEXT NOT NULL,after_json TEXT NOT NULL,saved_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reports (report_id TEXT PRIMARY KEY,payload TEXT NOT NULL,created_at TEXT NOT NULL);
            ''')
            for table in ('units','metadata','events','reports'):
                for action in ('UPDATE','DELETE'):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action} BEFORE {action} ON {table} "
                               "BEGIN SELECT RAISE(ABORT,'Immutable creator review history'); END")
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute("SELECT payload FROM metadata WHERE key='session'").fetchone()
            if existing:
                if json.loads(existing[0])['source_sha256']!=source_hash:
                    raise CreatorReviewConflict('Session belongs to another snapshot; use a new review database')
                return
            metadata={'source_path':str(source.resolve()),'source_sha256':source_hash,
                      'session_id':fingerprint([source_hash,'creator-review-v1'])[:24],
                      'schema_version':'creator-review-v1','source_manifest':snapshot.get('manifest',{}),
                      'created_at':datetime.now(timezone.utc).isoformat(),
                      'selection':'profiles plus seeded or explicit screened topic pairs; not all possible negatives'}
            db.execute('INSERT INTO metadata VALUES (?,?)',('session',encoded(metadata)))
            for unit in units:
                db.execute('INSERT INTO units VALUES (?,?,?,?,?,?)',(unit['unit_id'],unit['unit_type'],
                    unit['creator_id'],unit['topic_id'],unit['readiness_group'],encoded(unit)))
                db.execute('INSERT INTO reviews VALUES (?,?,?)',(unit['unit_id'],0,encoded(blank_review())))

    def metadata(self):
        with self.connect() as db:
            return json.loads(db.execute("SELECT payload FROM metadata WHERE key='session'").fetchone()[0])

    def records(self):
        with self.connect() as db:
            rows=db.execute('SELECT units.payload AS frozen,reviews.payload AS review FROM units JOIN reviews USING(unit_id) ORDER BY unit_id').fetchall()
        return [{'fixed':json.loads(row['frozen']),'review':json.loads(row['review'])} for row in rows]

    def record(self,identifier):
        with self.connect() as db:
            row=db.execute('SELECT units.payload AS frozen,reviews.payload AS review FROM units JOIN reviews USING(unit_id) WHERE unit_id=?',(identifier,)).fetchone()
        if row is None:
            raise KeyError('Unknown fixed review unit')
        return {'fixed':json.loads(row['frozen']),'review':json.loads(row['review'])}

    def summary(self):
        records=self.records()
        result={'session':self.metadata(),'units':[],'by_type':{},'by_group':{}}
        for row in records:
            fixed,review=row['fixed'],row['review']
            result['units'].append({key:fixed[key] for key in ('unit_id','unit_type','creator_id','topic_id','display_name','readiness_group')}
                |{'human_label':review['human_label'],'revision':review['revision']})
        for key in ('profile','affinity'):
            selected=[r for r in records if r['fixed']['unit_type']==key]
            result['by_type'][key]={'total':len(selected),'reviewed':sum(r['review']['human_label'] is not None for r in selected)}
        for group in ('review_ready','insufficient'):
            selected=[r for r in records if r['fixed']['readiness_group']==group]
            result['by_group'][group]={'total':len(selected),'reviewed':sum(r['review']['human_label'] is not None for r in selected)}
        result['ready']=all(row['review']['human_label'] is not None for row in records) and bool(records)
        return result

    def save(self,payload):
        fields={'unit_id','revision','human_label','human_domains','human_specializations','selected_video_ids',
                'evidence_sufficiency','explanation_support','notes','reviewer','review_basis','reset'}
        if not isinstance(payload,dict) or set(payload)-fields:
            raise ValueError('Only explicit human review fields can be edited')
        if type(payload.get('revision')) is not int or type(payload.get('reset',False)) is not bool:
            raise ValueError('Integer revision and boolean reset are required')
        identifier=payload.get('unit_id')
        if not isinstance(identifier,str):
            raise ValueError('A fixed unit ID is required')
        row=self.record(identifier)
        fixed=row['fixed']
        reviewer=payload.get('reviewer','')
        if not isinstance(reviewer,str) or not reviewer.strip() or len(reviewer)>120:
            raise ValueError('Reviewer name is required (maximum 120 characters)')
        notes=payload.get('notes','')
        if not isinstance(notes,str) or len(notes)>6000:
            raise ValueError('Notes must be text, maximum 6000 characters')
        after=blank_review()
        if not payload.get('reset'):
            label=payload.get('human_label')
            if label not in (PROFILE_LABELS if fixed['unit_type']=='profile' else AFFINITY_LABELS):
                raise ValueError('Select a valid human label')
            if payload.get('evidence_sufficiency') not in SUFFICIENCY or payload.get('explanation_support') not in EXPLANATIONS:
                raise ValueError('Explicit evidence sufficiency and explanation support judgments are required')
            if payload.get('review_basis') not in ('human_evidence_review','assisted_review'):
                raise ValueError('Choose the actual review basis')
            if not notes.strip():
                raise ValueError('A short evidence-based review note is required')
            values={}
            for key,allowed in [('human_domains',DOMAINS),('human_specializations',SPECIALIZATIONS)]:
                value=payload.get(key,[])
                if not isinstance(value,list) or any(not isinstance(x,str) or x not in allowed for x in value) or len(set(value))!=len(value):
                    raise ValueError('Invalid or duplicate classification values')
                values[key]=value
            video_ids=payload.get('selected_video_ids',[])
            video_map={v['video_id']:v for v in fixed['videos']+fixed.get('prior_videos',[])}
            if not isinstance(video_ids,list) or any(not isinstance(x,str) or x not in video_map for x in video_ids) or len(set(video_ids))!=len(video_ids):
                raise ValueError('Evidence must reference unique videos from this fixed unit')
            dates={timestamp(video_map[x]['published_at']).date() for x in video_ids}
            if label=='insufficient_evidence':
                if payload['evidence_sufficiency']!='insufficient' or any(values.values()):
                    raise ValueError('Insufficient evidence cannot finalize classifications')
            elif payload['evidence_sufficiency']=='insufficient':
                raise ValueError('Use the insufficient_evidence label for insufficient evidence')
            if fixed['unit_type']=='profile':
                if values['human_specializations'] and 'beauty' not in values['human_domains']:
                    raise ValueError('Beauty specializations require the beauty domain')
                if label in ('supported','partially_supported') and (not values['human_domains'] or not video_ids):
                    raise ValueError('An approved/partial profile requires explicit domains and video evidence')
                if label=='supported' and (len(video_ids)<2 or len(dates)<2):
                    raise ValueError('One video or one publication date cannot establish a stable supported profile')
            else:
                if any(values.values()):
                    raise ValueError('Edit classifications in the separate profile review')
                if label in ('strong_affinity','moderate_affinity') and (len(video_ids)<2 or len(dates)<2):
                    raise ValueError('Sustained affinity requires multiple relevant videos on distinct dates')
                if label=='weak_affinity' and not video_ids:
                    raise ValueError('Weak affinity requires at least one relevant video')
                if label=='no_affinity' and video_ids:
                    raise ValueError('No-affinity review cannot also approve relevant videos')
            after.update({key:payload.get(key) for key in ('human_label','evidence_sufficiency','explanation_support','review_basis')})
            after.update(values,selected_video_ids=video_ids)
        after.update(reviewer=reviewer.strip(),notes=notes.strip(),saved_at=datetime.now(timezone.utc).isoformat())
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT * FROM reviews WHERE unit_id=?',(identifier,)).fetchone()
            if current['revision']!=payload['revision']:
                raise CreatorReviewConflict('This row changed in another tab; reload before saving')
            after['revision']=current['revision']+1
            db.execute('UPDATE reviews SET revision=?,payload=? WHERE unit_id=?',
                       (after['revision'],encoded(after),identifier))
            db.execute('INSERT INTO events(unit_id,before_json,after_json,saved_at) VALUES (?,?,?,?)',
                       (identifier,current['payload'],encoded(after),after['saved_at']))
        return after

    def history(self,identifier):
        self.record(identifier)
        with self.connect() as db:
            return [{'event_id':row['event_id'],'before':json.loads(row['before_json']),
                     'after':json.loads(row['after_json']),'saved_at':row['saved_at']} for row in
                    db.execute('SELECT * FROM events WHERE unit_id=? ORDER BY event_id',(identifier,))]

    def export(self,kind=None):
        with self.connect() as db:
            db.execute('BEGIN')
            metadata=json.loads(db.execute("SELECT payload FROM metadata WHERE key='session'").fetchone()[0])
            rows=[{'fixed':json.loads(r['frozen']),'review':json.loads(r['review'])} for r in db.execute(
                'SELECT units.payload AS frozen,reviews.payload AS review FROM units JOIN reviews USING(unit_id) ORDER BY unit_id')]
            rows=[r for r in rows if kind is None or r['fixed']['unit_type']==kind]
            identifiers={r['fixed']['unit_id'] for r in rows}
            events=[{'unit_id':r['unit_id'],'event_id':r['event_id'],'before':json.loads(r['before_json']),
                     'after':json.loads(r['after_json']),'saved_at':r['saved_at']} for r in
                    db.execute('SELECT * FROM events ORDER BY event_id') if r['unit_id'] in identifiers]
        return {'session':metadata,'label_choices':{'profile':PROFILE_LABELS,'affinity':AFFINITY_LABELS},
                'rows':rows,'revision_history':events,
                'notice':'Explicit saved reviews with review_basis; not automatically independent human gold'}

    def finalize(self):
        from .creator_review_evaluation import evaluate
        records=self.records()
        if not records or any(row['review']['human_label'] is None for row in records):
            return {'state':'pending','progress':self.summary(),'reason':'Complete both review units before final evaluation'}
        report=evaluate(records)
        report.update(session=self.metadata(),review_revision_hash=fingerprint(records))
        identifier=fingerprint(report)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO reports VALUES (?,?,?)',
                (identifier,encoded(report),datetime.now(timezone.utc).isoformat()))
        return report
