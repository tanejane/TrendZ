"""Pure Phase 6A identities. No evidence, popularity, database or reach estimator."""
from decimal import Decimal, localcontext, ROUND_CEILING, ROUND_HALF_UP
from .campaign_schema import CALCULATION_VERSION


def unavailable(reason, unit):
    return {'state': 'unavailable', 'value': None, 'unit': unit, 'reason': reason,
            'category': 'derived_output', 'formula_version': CALCULATION_VERSION}


def value(number, unit):
    display = number.quantize(Decimal('.01'), rounding=ROUND_HALF_UP) if unit in ('MYR', 'percent') else number
    return {'state': 'available', 'value': format(number, 'f'), 'display_value': format(display, 'f'),
            'unit': unit, 'category': 'derived_output', 'formula_version': CALCULATION_VERSION}


def calculate(a):
    with localcontext() as context:
        context.prec = 50
        return _calculate(a)


def _calculate(a):
    def number(v): return None if v is None else Decimal(v)
    costs = [number(v) for v in a['costs'].values()]
    cost = sum(costs, Decimal(0)) if all(c is not None for c in costs) else None
    total = value(cost, 'MYR') if cost is not None else unavailable('Supply all four costs; enter zero explicitly', 'MYR')
    budget = number(a['budget_ceiling'])
    headroom = value(budget - cost, 'MYR') if budget is not None and cost is not None else unavailable('Budget ceiling and all costs required', 'MYR')
    n, aov, margin = number(a['population']['value']), number(a['aov']), number(a['gross_margin_rate'])
    conversion = a['objective'] == 'conversion'
    reason = 'Objective is cost-only in this calculation version' if not conversion else 'Missing required commercial assumptions'
    rows = []
    for name in ('low', 'base', 'high'):
        rate = number(a['conversion_rates'][name])
        orders = n * rate if conversion and n is not None and rate is not None else None
        revenue = orders * aov if orders is not None and aov is not None else None
        gross = revenue * margin if revenue is not None and margin is not None else None
        net = gross - cost if gross is not None and cost is not None else None
        roi = net / cost if net is not None and cost != 0 else None
        def output(v, unit): return value(v, unit) if v is not None else unavailable(reason, unit)
        rows.append({'scenario': name, 'changed_variable': 'assumed_conversion_rate', 'assumed_conversion_rate': a['conversion_rates'][name],
                     'modeled_conversions': output(orders, 'orders'), 'modeled_revenue': output(revenue, 'MYR'),
                     'modeled_gross_profit': output(gross, 'MYR'), 'modeled_net_profit': output(net, 'MYR'),
                     'modeled_roi': value(roi, 'ratio') if roi is not None else unavailable('Zero total cost: ROI undefined' if cost == 0 else reason, 'ratio'),
                     'modeled_roi_percent': value(roi * 100, 'percent') if roi is not None else unavailable('Zero total cost: ROI undefined' if cost == 0 else reason, 'percent')})
    def threshold(denominator, unit, needs_n=False):
        if not conversion or cost is None:
            return unavailable(reason, unit)
        if needs_n and (n is None or n == 0):
            return unavailable('Positive supplied population required for a break-even conversion rate', unit)
        if denominator is None or denominator <= 0:
            if cost == 0 and not needs_n:
                return value(Decimal(0), unit)
            return unavailable('No finite break-even with missing/zero denominator', unit)
        return value(cost / denominator, unit)
    per_order = aov * margin if aov is not None and margin is not None else None
    break_even = {'revenue': threshold(margin, 'MYR'), 'conversions': threshold(per_order, 'orders'),
                  'conversion_rate': threshold(n * per_order if n is not None and per_order is not None else None, 'ratio', True)}
    orders_be = break_even['conversions']
    break_even['minimum_whole_orders'] = value(Decimal(orders_be['value']).to_integral_value(rounding=ROUND_CEILING), 'orders') if orders_be['state'] == 'available' else unavailable(orders_be['reason'], 'orders')
    rate_be = break_even['conversion_rate']
    break_even['conversion_rate_percent'] = value(Decimal(rate_be['value']) * 100, 'percent') if rate_be['state'] == 'available' else unavailable(rate_be['reason'], 'percent')
    break_even['feasibility'] = ('infeasible_under_assumptions' if Decimal(rate_be['value']) > 1 else 'within_one_order_per_person_bound') if rate_be['state'] == 'available' else 'unavailable'
    break_even['assumptions_required'] = ['all four costs', 'positive AOV and gross margin for orders', 'positive supplied unique-person population for rate']
    base = rows[1]
    explanation = 'Costs only under the selected objective; conversion economics are unavailable.'
    if conversion and base['modeled_conversions']['state'] == 'available':
        basis = 'an assumed reach' if a['conversion_basis'] == 'assumed_reach' else 'an assumed target population'
        rate_percent = Decimal(a['conversion_rates']['base']) * 100
        explanation = (f"At {basis} of {a['population']['value']} people and an assumed conversion rate of "
                       f"{rate_percent}%, this scenario models {base['modeled_conversions']['value']} orders under these inputs.")
    elif conversion:
        explanation = 'Conversion economics remain unavailable until their required assumptions are supplied.'
    return {'calculated_outcomes': {'total_cost': total, 'budget_headroom': headroom, 'base': base},
            'sensitivity': rows, 'break_even': break_even, 'scenario_explanation': explanation,
            'scenario_state': 'evaluated' if (base['modeled_roi']['state'] == 'available' if conversion else total['state'] == 'available') else 'partial'}
