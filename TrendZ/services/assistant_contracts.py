"""Provider-neutral, closed tool contracts. This module registers no model tools."""
import json
import re
from .campaign_schema import OBJECTIVES, FORMATS, COSTS
from .creator_candidates import PINS

VERSION = 'trendz-assistant-tools-v1'
BASES = ('observed', 'reviewed', 'upstream_calculated', 'diagnostic', 'user_assumption', 'derived_scenario', 'workflow_request')


class AssistantError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def obj(properties, required=None):
    return {'type': 'object', 'properties': properties, 'required': list(properties) if required is None else required,
            'additionalProperties': False}


def string(enum=None, maximum=200):
    return {'type': 'string', 'minLength': 1, 'maxLength': maximum, **({'enum': list(enum)} if enum else {})}


def optional(schema):
    return {'anyOf': [schema, {'type': 'null'}]}


MONEY = optional({'anyOf': [{'type': 'string', 'pattern': r'^\d+(?:\.\d{1,12})?$', 'maxLength': 40},
                           {'type': 'integer', 'minimum': 0, 'maximum': 10**12}]})
SCOPE = {'topic_id': string(), 'query_id': string(), 'market': string(('MY',))}
REQUIREMENTS = {'required_market_evidence': string(('optional', 'verified')),
                'engagement_requirement': string(('optional', 'available', 'five_valid_samples'))}
ASSUMPTIONS = obj({
    'objective': string(OBJECTIVES), 'format': string(FORMATS), 'channel': string(('youtube',)), 'currency': string(('MYR',)),
    'campaign_window': obj({'start_date': string(maximum=10), 'end_date_exclusive': string(maximum=10)}),
    'costs': obj({k: MONEY for k in COSTS}, []), 'budget_ceiling': MONEY,
    'conversion_basis': optional(string(('assumed_reach', 'target_population'))),
    'population': obj({'value': optional({'type': 'integer', 'minimum': 0, 'maximum': 10**12}),
        'unit': optional(string(('unique_reached_people', 'target_people'))),
        'basis': optional(string(('user_entered', 'external_planning'))), 'source_ref': optional(string(maximum=2000))}, []),
    'conversion_rates': obj({k: MONEY for k in ('low', 'base', 'high')}, []),
    'aov': MONEY, 'gross_margin_rate': MONEY,
    'manual_candidate_acknowledgement': obj({'accepted': {'type': 'boolean'}, 'reason': optional(string(maximum=4000))}, []),
    'source_notes': optional({'type': 'string', 'maxLength': 4000})},
    ['objective', 'format', 'channel', 'currency', 'campaign_window'])
PIN_FIELDS = {**{k: string((v,)) for k, v in PINS.items()}, **SCOPE,
    'product_id': string(), 'creator_id': string(), **REQUIREMENTS,
    'trend_method_version': string(('intelligence-dimensions-v1',)),
    **{k: {'type': 'string', 'pattern': r'^[a-f0-9]{64}$'} for k in (
        'trend_snapshot_sha256', 'topic_config_sha256', 'product_assessment_sha256', 'candidate_sha256', 'context_sha256')}}
PRODUCT = {**SCOPE, 'product_id': string()}
CREATOR = {**PRODUCT, 'creator_id': string()}


def tool(properties, optional_keys=()):
    properties = {'context_ref': string(), **properties}
    return obj(properties, [k for k in properties if k not in optional_keys])


PAGE = {'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20}, 'offset': {'type': 'integer', 'minimum': 0, 'maximum': 1000}}
SCHEMAS = {
    'get_trend_intelligence': tool(SCOPE),
    'compare_trends': tool({'topics': {'type': 'array', 'items': obj(SCOPE), 'minItems': 2, 'maxItems': 4, 'uniqueItems': True}}),
    'get_product_fit': tool(PRODUCT),
    'list_positive_product_fits': tool({**SCOPE, **PAGE}, PAGE),
    'get_creator_candidates': tool({**PRODUCT, **REQUIREMENTS, **PAGE}, (*PAGE, *REQUIREMENTS)),
    'get_creator_candidate_evidence': tool(CREATOR),
    'get_campaign_context': tool({**CREATOR, **REQUIREMENTS, 'calculation_version': string(('campaign-economics-v1',))}, REQUIREMENTS),
    'evaluate_campaign_scenario': tool({'context_pins': obj(PIN_FIELDS), 'assumptions': ASSUMPTIONS,
        'schema_version': string(('campaign-scenario-v1',)), 'calculation_version': string(('campaign-economics-v1',)),
        'confirmation_ref': string()}),
    'trace_decision': tool({**CREATOR, 'scenario_result_ref': string()}, ('scenario_result_ref',)),
}


def validate(value, schema, path='$'):
    """Validate the deliberately limited JSON Schema subset used by SCHEMAS."""
    if not schema:
        return  # Opaque delivered value/scope is checked against immutable bytes by grounding.
    if 'anyOf' in schema:
        for branch in schema['anyOf']:
            try:
                validate(value, branch, path)
                return
            except AssistantError:
                pass
        raise AssistantError('invalid_schema', path + ': incompatible value')
    kind = schema.get('type')
    types = {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool}
    if kind == 'null':
        if value is not None: raise AssistantError('invalid_schema', path + ': expected null')
        return
    if not isinstance(value, types[kind]) or kind == 'integer' and isinstance(value, bool):
        raise AssistantError('invalid_schema', path + ': incorrect type')
    if 'enum' in schema and value not in schema['enum']:
        raise AssistantError('invalid_schema', path + ': unsupported choice')
    if kind == 'object':
        if set(value) - set(schema['properties']) or set(schema['required']) - set(value):
            raise AssistantError('invalid_schema', path + ': missing or unknown properties')
        for key, item in value.items(): validate(item, schema['properties'][key], path + '/' + key)
    if kind == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', 1000):
            raise AssistantError('invalid_schema', path + ': invalid array size')
        if schema.get('uniqueItems') and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            raise AssistantError('invalid_schema', path + ': duplicate items')
        for i, item in enumerate(value): validate(item, schema['items'], path + '/' + str(i))
    if kind == 'string':
        if not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', 10000) or ('pattern' in schema and re.fullmatch(schema['pattern'], value) is None):
            raise AssistantError('invalid_schema', path + ': invalid string')
    if kind == 'integer' and not schema.get('minimum', -10**15) <= value <= schema.get('maximum', 10**15):
        raise AssistantError('invalid_schema', path + ': out of range')
