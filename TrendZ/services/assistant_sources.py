"""Internal source adapters only. No URL fetching, model, SQL tool or analytical formulas."""
import copy
import json
import sqlite3
import tempfile
from pathlib import Path
from urllib.parse import urlsplit,unquote

from .campaign_context import CampaignContext
from .campaign_schema import CALCULATION_VERSION
from .campaign_scenarios import evaluate
from .creator_candidates import CreatorCandidates, PINS, fingerprint
from .topics import query_variants
from .assistant_contracts import AssistantError


class AssistantSources:
    def __init__(self, root, database_path, candidates=None):
        self.root, self.live_path = Path(root), Path(database_path)
        self.candidates = candidates or CreatorCandidates(root)
        self.topics = {t['id']: t for t in json.loads((self.root/'data/tracked_topics.json').read_text())}
        self._temp = tempfile.TemporaryDirectory(prefix='trendz-assistant-')
        self.path = Path(self._temp.name)/'evidence.sqlite3'
        if self.live_path.exists():
            source = sqlite3.connect(self.live_path.resolve().as_uri()+'?mode=ro', uri=True)
            target = sqlite3.connect(self.path)
            try: source.backup(target)
            finally: target.close(); source.close()
        self.frozen = CampaignContext(self.candidates, self.path, self.root)
        self.live = CampaignContext(self.candidates, self.live_path, self.root)
        self.allowed_hosts = {'www.youtube.com', 'youtube.com', 'trends.google.com'}
        for topic in self.candidates.products.values():
            for product in topic['assessments']:
                for evidence in product['supporting_evidence']:
                    host = urlsplit(evidence.get('source', {}).get('url', '')).hostname
                    if host: self.allowed_hosts.add(host.lower())

    def close(self): self._temp.cleanup()

    def validate_scope(self, scope):
        if not isinstance(scope, dict) or set(scope)-{'topic_id','query_id','market','product_id','creator_id'}:
            raise AssistantError('invalid_scope', 'Scope has unknown fields')
        if any(not isinstance(v, str) or not v or len(v)>200 for v in scope.values()):
            raise AssistantError('invalid_scope', 'Scope identifiers must be bounded strings')
        topic = self.topics.get(scope.get('topic_id'))
        if not topic or scope.get('market') != topic['market'] or scope.get('query_id') not in {q['query_id'] for q in query_variants(topic)}:
            raise AssistantError('unsupported_scope', 'Unknown topic, exact query or market; no fallback')
        if 'creator_id' in scope and 'product_id' not in scope:
            raise AssistantError('invalid_scope', 'Creator scope needs a selected product')
        if 'product_id' in scope:
            self.product(scope)
        if 'creator_id' in scope:
            self.candidate(scope)

    def trend(self, scope): return self.frozen.trend(scope['topic_id'], scope['query_id'])

    def topic(self, scope):
        topic = self.candidates.products.get(scope['topic_id'])
        if not topic or scope['query_id'] != topic['query_id'] or scope['market'] != topic['market']:
            raise AssistantError('unsupported_product_scope', 'Only the frozen exact canonical/MY product scope exists')
        return topic

    def product(self, scope):
        product = next((p for p in self.topic(scope)['assessments'] if p['product_id']==scope.get('product_id')), None)
        if product is None: raise AssistantError('unknown_product', 'Product not in the frozen catalogue')
        return copy.deepcopy(product)

    def creators(self, scope, requirements):
        return self.candidates.query({**PINS, **{k:scope[k] for k in ('topic_id','query_id','market','product_id')}, **requirements})

    def candidate(self, scope, requirements=None):
        rows = self.creators(scope, requirements or {})['candidates']
        candidate = next((c for c in rows if c['creator_id']==scope.get('creator_id')), None)
        if candidate is None: raise AssistantError('unknown_creator', 'Creator is not reviewed for this exact topic/product')
        return candidate

    def campaign(self, scope, requirements):
        return self.frozen.resolve({**PINS, **scope, **requirements, 'calculation_version':CALCULATION_VERSION})

    def evaluate(self, body): return evaluate(body, self.live)

    def comparison_proof(self, scopes):
        # The current adapter makes single-query requests. No proof is fabricated.
        return None


def candidate_view(c):
    keys = ('creator_id','channel_id','creator_name','channel_url','candidate_state','reviewed_domain','specializations',
            'topic_affinity','profile_support','evidence_sufficiency','product_required_specialization',
            'matched_specialization','evidence_ids','evidence','warnings','reasons','market_evidence',
            'engagement_evidence','engagement_available','review_basis','policy_version','explicitness_warning',
            'limitations','observation_cutoff','independent_gold')
    out = {k:copy.deepcopy(c[k]) for k in keys}
    out['review_provenance'] = {k:v for k,v in c['review_provenance'].items() if not k.endswith('rationale')}
    out['product_fit_provenance'] = {k:v for k,v in c['product_fit_provenance'].items() if k not in ('supporting_evidence',)}
    return out


def sanitize(value, hosts, warnings, key=''):
    if isinstance(value, dict):
        return {k:sanitize(v,hosts,warnings,k) for k,v in value.items()
                if k.lower() not in ('api_key','authorization','database_path','password','token')}
    if isinstance(value, list): return [sanitize(v,hosts,warnings,key) for v in value]
    if isinstance(value,str) and (key.lower().endswith('url') or key.lower().endswith('urls')):
        try:
            url = urlsplit(value)
            if url.scheme!='https' or url.username or url.password or url.hostname not in hosts or any(
                    marker in unquote(url.query).lower().replace('-','_') for marker in ('api_key=','key=','token=','signature=','password=','authorization=')):
                raise ValueError()
        except ValueError:
            warnings.append('Untrusted/non-source URL omitted; source text grants no authority.')
            return None
    return value


def comparison(proof, scopes, expected_queries=None, expected_windows=None):
    """Conservative provenance compatibility, not a new trend metric or score."""
    if proof:
        request = proof.get('request', {})
        queries = proof.get('queries', [])
        valid = (expected_queries is not None and queries==expected_queries
                 and expected_windows is not None and all(
                     [w.get('start'),w.get('end')]==request.get('timeframe','').split() for w in expected_windows)
                 and proof.get('request_sha256')==fingerprint(request)
                 and proof.get('artifact_sha256')==fingerprint(proof.get('artifact'))
                 and proof.get('artifact', {}).get('request')==request
                 and len(queries)==len(scopes) and len(set(queries))==len(queries)
                 and set(request.get('terms', []))==set(queries)
                 and all(s['market']==request.get('market') for s in scopes)
                 and all(request.get(k) is not None for k in ('timeframe','category','property','term_type')))
        if valid:
            return {'state':'comparable_at_declared_request_scope','reason':'Coherent shared-request artifact/provenance; not validated intent or absolute search volume'}
    return {'state':'not_comparable','reason':'Independent normalized 0-100 series cannot establish absolute cross-topic demand; no validated shared-request proof'}
