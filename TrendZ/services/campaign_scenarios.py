"""Stateless orchestration; sources are read-only, commercial quantities explicit."""
import copy
from datetime import datetime, timezone
from decimal import Decimal

from .campaign_context import CONTEXT_INPUTS
from .campaign_economics import calculate
from .campaign_schema import CALCULATION_VERSION, SCHEMA_VERSION, ScenarioError, fields, normalize_assumptions
from .creator_candidates import fingerprint


def evaluate(body, context_service):
    fields(body, ('schema_version', 'context_ref', 'calculation_version', 'assumptions'), 'request')
    if body.get('schema_version') != SCHEMA_VERSION:
        raise ScenarioError('schema_version_mismatch', 'Required schema_version: ' + SCHEMA_VERSION, 400)
    if not body.get('calculation_version'):
        raise ScenarioError('missing_pin', 'Required calculation_version is missing', 400)
    if body.get('calculation_version') != CALCULATION_VERSION:
        raise ScenarioError('calculation_version_mismatch', 'Scenario calculation version mismatch', 409)
    ref = body.get('context_ref')
    if not isinstance(ref, dict):
        raise ScenarioError('missing_context', 'A pinned context_ref is required', 400)
    source_params = {k: v for k, v in ref.items() if k in CONTEXT_INPUTS}
    source_params['calculation_version'] = body['calculation_version']
    context = context_service.resolve(source_params)
    if set(ref) != set(context['context_ref']):
        raise ScenarioError('missing_or_unknown_pin', 'Supply exactly the complete context_ref from context bootstrap', 400)
    if ref != context['context_ref']:
        raise ScenarioError('stale_context', 'Upstream evidence/version changed; refresh context explicitly', 409)
    if not context['scenario_eligible']:
        raise ScenarioError('blocked_candidate', 'Positive Product Fit and a usable creator candidate are required; unavailable/ineligible cannot be overridden')
    a = normalize_assumptions(body.get('assumptions'))
    candidate = context['evidence']['creator_candidate']
    ack = a['manual_candidate_acknowledgement']
    if candidate['candidate_state'] == 'manual_review_only' and (not ack['accepted'] or not (ack['reason'] or '').strip()):
        raise ScenarioError('manual_acknowledgement_required', 'Manual-review-only requires explicit acceptance and a reason', 409)
    outcomes = calculate(a)
    warnings = list(context['warnings'])
    headroom = outcomes['calculated_outcomes']['budget_headroom']
    if headroom['state'] == 'available' and Decimal(headroom['value']) < 0:
        warnings.append('Supplied costs exceed the budget ceiling; costs have not been capped.')
    if outcomes['break_even']['feasibility'] == 'infeasible_under_assumptions':
        warnings.append('Break-even exceeds 100% conversion in the one-order-per-person model.')
    if a['population']['value'] is None:
        warnings.append('Reach/population is unavailable; no creator or trend metrics have been substituted.')
    if a['objective'] != 'conversion':
        warnings.append('Awareness/consideration are cost-only; this version has no monetization model for them.')
    assumption_provenance = {'category': 'business_assumption',
        'basis': 'Explicit user submission; no values inferred from evidence',
        'population_basis': a['population']['basis'], 'population_source_ref': a['population']['source_ref'],
        'source_notes': a['source_notes']}
    return copy.deepcopy({**outcomes, 'data_mode': 'assumption_based', 'output_kind': 'assumption_based', 'is_prediction': False,
        'evidence': context['evidence'], 'assumptions': a, 'warnings': warnings,
        'provenance': {'context_ref': context['context_ref'], 'schema_version': SCHEMA_VERSION,
            'calculation_version': CALCULATION_VERSION, 'assumption_provenance': assumption_provenance,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'scenario_fingerprint': fingerprint({'context': ref, 'assumptions': a, 'calculation_version': CALCULATION_VERSION})},
        'field_classification': {'evidence': 'evidence (observed, reviewed or upstream-calculated; not commercial assumptions)',
            'assumptions': 'business_assumption', 'calculated_outcomes': 'derived_output', 'sensitivity': 'derived_output',
            'break_even': 'derived_output', 'scenario_explanation': 'derived_output', 'provenance': 'attached metadata',
            'sensitivity.assumed_conversion_rate': 'business_assumption',
            'calculated_outcomes.base.assumed_conversion_rate': 'business_assumption'},
        'limitations': context['limitations'] + ['Gross margin includes COGS, not campaign spend; avoid double-counting fulfilment/fees.',
            'Modeled net profit is campaign contribution under assumptions, not audited company net income.',
            'Break-even time and success probabilities are unavailable; sensitivity rows are not confidence intervals.']})
