"""Explicit campaign assumptions. Missing is not zero; rates are fractions."""
import re
from datetime import date
from decimal import Decimal

CALCULATION_VERSION = 'campaign-economics-v1'
SCHEMA_VERSION = 'campaign-scenario-v1'
OBJECTIVES = ('awareness', 'consideration', 'conversion')
FORMATS = ('tutorial', 'product_review', 'routine_integration', 'educational_explainer',
           'short_form_demonstration', 'creator_led_promotional_post')
COSTS = ('creator_fee', 'media_spend', 'production_cost', 'other_cost')


class ScenarioError(ValueError):
    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code, self.status = code, status


def fields(value, allowed, name):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ScenarioError('invalid_schema', name + ' must be an object with supported fields only', 400)


def decimal_value(value, name, maximum=Decimal('1000000000000')):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r'\d+(?:\.\d{1,12})?', str(value)) or len(str(value)) > 40:
        raise ScenarioError('invalid_number', name + ': use a finite nonnegative decimal string (up to 12 decimal places)')
    number = Decimal(value)
    if number > maximum:
        raise ScenarioError('out_of_range', name + ' exceeds its allowed bound')
    return format(number.normalize(), 'f')


def normalize_assumptions(a):
    fields(a, ('objective', 'format', 'channel', 'currency', 'campaign_window', 'costs', 'budget_ceiling',
               'conversion_basis', 'population', 'conversion_rates', 'aov', 'gross_margin_rate',
               'manual_candidate_acknowledgement', 'source_notes'), 'assumptions')
    for key, choices in [('objective', OBJECTIVES), ('format', FORMATS), ('channel', ('youtube',)), ('currency', ('MYR',))]:
        if a.get(key) not in choices:
            raise ScenarioError('invalid_choice', key + ' requires an explicit supported choice')
    window = a.get('campaign_window', {})
    fields(window, ('start_date', 'end_date_exclusive'), 'campaign_window')
    try:
        if any(not isinstance(window.get(k), str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', window[k]) for k in ('start_date', 'end_date_exclusive')):
            raise ValueError('Noncanonical date')
        start, end = [date.fromisoformat(window[k]) for k in ('start_date', 'end_date_exclusive')]
    except (KeyError, TypeError, ValueError):
        raise ScenarioError('invalid_dates', 'Supply both campaign dates as YYYY-MM-DD')
    if not 0 < (end - start).days <= 3660:
        raise ScenarioError('invalid_dates', 'Campaign window must be positive and at most 3660 days')
    costs = a.get('costs', {})
    fields(costs, COSTS, 'costs')
    rates = a.get('conversion_rates', {})
    fields(rates, ('low', 'base', 'high'), 'conversion_rates')
    rates = {k: decimal_value(rates.get(k), 'conversion_rates.' + k, Decimal(1)) for k in ('low', 'base', 'high')}
    pairs = [('low', 'base'), ('base', 'high'), ('low', 'high')]
    if any(rates[x] is not None and rates[y] is not None and Decimal(rates[x]) > Decimal(rates[y]) for x, y in pairs):
        raise ScenarioError('inverted_range', 'Conversion assumptions must satisfy low <= base <= high')
    basis = a.get('conversion_basis')
    if basis not in (None, 'assumed_reach', 'target_population'):
        raise ScenarioError('invalid_basis', 'Use assumed_reach or target_population')
    population = a.get('population', {})
    fields(population, ('value', 'unit', 'basis', 'source_ref'), 'population')
    count = population.get('value')
    if count is not None and (isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 10**12):
        raise ScenarioError('invalid_population', 'Population must be a nonnegative integer up to 10^12')
    if count is not None:
        unit = {'assumed_reach': 'unique_reached_people', 'target_population': 'target_people'}.get(basis)
        if not unit or population.get('unit') != unit:
            raise ScenarioError('invalid_population_unit', 'Select exactly one population basis with matching unique-person units')
        if population.get('basis') not in ('user_entered', 'external_planning'):
            raise ScenarioError('invalid_assumption_source', 'Reach/population needs an explicit assumption source')
        if population.get('basis') == 'external_planning' and (not isinstance(population.get('source_ref'), str) or not population['source_ref'].strip()):
            raise ScenarioError('missing_planning_source', 'Externally planned reach needs a source reference')
    for key in ('source_ref',):
        if population.get(key) is not None and (not isinstance(population[key], str) or len(population[key]) > 2000):
            raise ScenarioError('invalid_text', 'Planning source reference must be text up to 2000 characters')
    ack = a.get('manual_candidate_acknowledgement', {})
    fields(ack, ('accepted', 'reason'), 'manual_candidate_acknowledgement')
    if not isinstance(ack.get('accepted', False), bool):
        raise ScenarioError('invalid_acknowledgement', 'Acknowledgement must be boolean')
    for value in (ack.get('reason'), a.get('source_notes')):
        if value is not None and (not isinstance(value, str) or len(value) > 4000):
            raise ScenarioError('invalid_text', 'Notes/reason must be text up to 4000 characters')
    return {
        'objective': a['objective'], 'format': a['format'], 'channel': a['channel'], 'currency': a['currency'],
        'campaign_window': dict(window),
        'costs': {k: decimal_value(costs.get(k), 'costs.' + k) for k in COSTS},
        'budget_ceiling': decimal_value(a.get('budget_ceiling'), 'budget_ceiling'),
        'conversion_basis': basis, 'population': {'value': count, 'unit': population.get('unit'),
            'basis': population.get('basis'), 'source_ref': population.get('source_ref')},
        'conversion_rates': rates, 'aov': decimal_value(a.get('aov'), 'aov'),
        'gross_margin_rate': decimal_value(a.get('gross_margin_rate'), 'gross_margin_rate', Decimal(1)),
        'manual_candidate_acknowledgement': {'accepted': ack.get('accepted', False), 'reason': ack.get('reason')},
        'source_notes': a.get('source_notes')}
