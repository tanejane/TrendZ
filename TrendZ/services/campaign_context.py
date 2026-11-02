"""Read-only upstream resolution; temporary SQLite backup pins consistent trend evidence."""
import copy
import json
import sqlite3
import tempfile
from pathlib import Path

from .creator_candidates import PINS, fingerprint
from .intelligence_service import IntelligenceService
from .intelligence_evidence import read_evidence
from .topics import query_variants
from .campaign_schema import CALCULATION_VERSION, ScenarioError

IDENTITY_KEYS = ('topic_id', 'query_id', 'product_id', 'creator_id', 'market')
REQUIREMENT_KEYS = ('required_market_evidence', 'engagement_requirement')
CONTEXT_INPUTS = set(PINS) | set(IDENTITY_KEYS) | set(REQUIREMENT_KEYS) | {'calculation_version'}


class CampaignContext:
    def __init__(self, candidates, database_path, root):
        self.candidates, self.database_path, self.root = candidates, Path(database_path), Path(root)

    def trend(self, topic_id, query_id):
        topic_bytes = (self.root / 'data/tracked_topics.json').read_bytes()
        topics = json.loads(topic_bytes)
        topic = next(t for t in topics if t['id'] == topic_id)
        query = next(q for q in query_variants(topic) if q['query_id'] == query_id)

        def capture(path):
            dimensions = IntelligenceService(path, topics).topic(topic_id, query_id)
            raw = read_evidence(path, topic, query)
            manifest = {key: {'count': len(rows), 'sha256': fingerprint(sorted(fingerprint(row) for row in rows))}
                        for key, rows in raw.items()}
            manifest['topic_config_sha256'] = fingerprint(topics)
            return {'dimensions': dimensions, 'manifest': manifest,
                    'snapshot_sha256': fingerprint({'dimensions': dimensions, 'manifest': manifest})}

        if not self.database_path.exists():
            return capture(self.database_path)
        # Backup reads a consistent SQLite snapshot including committed WAL pages.
        # The disposable copy is not a persisted scenario or an upstream migration.
        with tempfile.TemporaryDirectory(prefix='trendz-campaign-') as directory:
            snapshot = Path(directory) / 'evidence.sqlite3'
            source = sqlite3.connect(self.database_path.resolve().as_uri() + '?mode=ro', uri=True)
            target = sqlite3.connect(snapshot)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
            return capture(snapshot)

    def resolve(self, params):
        if not isinstance(params, dict) or set(params) - CONTEXT_INPUTS:
            raise ScenarioError('invalid_context', 'Unsupported campaign context fields', 400)
        for key in set(PINS) | set(IDENTITY_KEYS) | {'calculation_version'}:
            if not isinstance(params.get(key), str) or not params[key]:
                raise ScenarioError('missing_pin', 'Missing context identity/version: ' + key, 400)
        if params['calculation_version'] != CALCULATION_VERSION:
            raise ScenarioError('calculation_version_mismatch', 'Scenario calculation version mismatch', 409)
        args = {k: v for k, v in params.items() if k not in ('creator_id', 'calculation_version')}
        result = self.candidates.query(args)
        candidate = next((r for r in result['candidates'] if r['creator_id'] == params['creator_id']), None)
        if candidate is None:
            raise ScenarioError('creator_not_reviewed', 'Creator is not in the fixed reviewed topic/query set', 404)
        trend = self.trend(params['topic_id'], params['query_id'])
        frozen_topic = self.candidates.products[params['topic_id']]
        if (trend['dimensions']['query'], trend['dimensions']['market']) != (frozen_topic['query'], frozen_topic['market']):
            raise ScenarioError('upstream_scope_conflict', 'Trend query/market conflicts with the frozen Product Fit/creator scope', 409)
        ref = {**PINS, **{k: params[k] for k in IDENTITY_KEYS}, **result['requirements'],
               'trend_method_version': trend['dimensions']['method_version'],
               'trend_snapshot_sha256': trend['snapshot_sha256'],
               'topic_config_sha256': trend['manifest']['topic_config_sha256'],
               'product_assessment_sha256': candidate['product_fit_provenance']['assessment_sha256'],
               'candidate_sha256': fingerprint(candidate)}
        ref['context_sha256'] = fingerprint({'ref': ref, 'calculation_version': CALCULATION_VERSION})
        product = candidate['product_fit_provenance']
        allowed = product['fit_state'] in ('direct_fit', 'supporting_fit') and candidate['candidate_state'] in (
            'strong_evidence_candidate', 'qualified_candidate', 'manual_review_only')
        warnings = ['Calculated under supplied assumptions, not measured or predicted campaign performance.',
                    'Campaign format is a planning assumption; creator format capability is not established.',
                    candidate['explicitness_warning'], *candidate['warnings']]
        if product['fit_state'] == 'supporting_fit':
            warnings.append('Supporting Fit is indirect compatibility, not direct product-topic alignment.')
        if candidate['candidate_state'] == 'manual_review_only':
            warnings.append('Manual-review-only candidate: explicit acknowledgement and reason required; state is not promoted.')
        if any(d['state'] != 'available' for d in trend['dimensions']['dimensions'].values()):
            warnings.append('Trend evidence includes provisional/unavailable dimensions; no commercial uplift is inferred.')
        return copy.deepcopy({'data_mode': 'real', 'context_ref': ref, 'calculation_version': CALCULATION_VERSION,
                'evidence': {'category': 'evidence', 'trend': trend['dimensions'], 'trend_manifest': trend['manifest'],
                             'product_fit': product, 'creator_candidate': candidate,
                             'basis': 'Observed sources plus separately reviewed/upstream-calculated states, not market truth'},
                'scenario_eligible': allowed, 'warnings': warnings,
                'limitations': candidate['limitations'] + [
                    'No sponsorship, willingness, product use or endorsement is established.',
                    'No causal incrementality, taxes, cash-flow timing or unmodeled returns/overheads are estimated.',
                    'Stateless: old source revisions may require exported artifacts for later evidence replay.']})
