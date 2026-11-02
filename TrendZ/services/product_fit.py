"""Deterministic catalogue fit, independent of observed demand and commercial value."""

import copy
import json
import re
from collections import Counter

from .product_catalogue import Catalogue, ROOT, normalize_ingredient

METHOD = 'product-fit-rules-1'
FIT_ORDER = {'direct_fit':0, 'supporting_fit':1, 'insufficient_evidence':2, 'no_fit':3}


def slug(value):
    return re.sub(r'[^a-z0-9]', '', value.lower())


class ProductFit:
    def __init__(self, catalogue=None):
        self.catalogue = catalogue or Catalogue()
        self.intents = json.loads((ROOT/'data/product_intents.json').read_text())
        self.topics = {t['id']:t for t in json.loads((ROOT/'data/tracked_topics.json').read_text())}

    def resolve(self, text):
        matches = []
        for topic_id in self.intents['topics']:
            topic = self.topics[topic_id]
            if slug(text) in {slug(topic_id), slug(topic['name']), slug(topic['query'])}:
                matches.append((topic_id, 'canonical'))
            for alias in topic.get('aliases', []):
                if slug(text) == slug(alias['query']):
                    matches.append((topic_id, alias['id']))
        unique = list(dict.fromkeys(matches))
        if not unique:
            raise KeyError('No configured Product Fit topic for this query')
        # Topic/name wins over a broad alias with the same wording.
        canonical = [match for match in unique if match[1] == 'canonical']
        return canonical[0] if len(canonical) == 1 else unique[0]

    def context(self, topic_id, query_id):
        if topic_id not in self.intents['topics']:
            raise KeyError('Unknown Product Fit topic')
        topic = self.topics[topic_id]
        queries = {'canonical':topic['query'], **{a['id']:a['query'] for a in topic.get('aliases', [])}}
        if query_id not in queries:
            raise KeyError('Unknown query ID for this topic')
        intent = copy.deepcopy(self.intents['topics'][topic_id])
        intent.update(intent.get('alias_overrides', {}).get(query_id, {}))
        return topic, queries[query_id], intent

    def assess(self, product, intent):
        evidence, missing, contradictions = [], [], []

        def read(field):
            refs = self.catalogue.evidence(product, field)
            if not refs:
                missing.append(field+' is missing or conflicted')
                return None
            evidence.extend(refs)
            return product[field]

        category, subcategory = read('category'), read('subcategory')
        market = read('market')
        areas, form = read('application_area'), read('product_format')
        area_ok = None if areas is None else bool(set(areas) & set(intent['areas']))
        form_ok = None if form is None else not intent['formats'] or form in intent['formats']
        category_ok = None if category is None else category in intent['categories']
        subcategory_ok = None if subcategory is None else not intent.get('subcategories') or subcategory in intent['subcategories']
        if area_ok is False:
            contradictions.append('application_area does not satisfy configured intent')
        if form_ok is False:
            contradictions.append('product_format does not satisfy configured intent')
        if category_ok is False:
            contradictions.append('category is incompatible; category alone never establishes fit')
        if subcategory_ok is False:
            contradictions.append('subcategory does not satisfy configured intent')
        if market is not None and market != 'MY':
            contradictions.append('catalogue market is not MY')
        wanted = intent.get('ingredients', [])
        ingredients = read('normalized_ingredients') if wanted else None
        ingredient_hits = sorted(set(map(normalize_ingredient, ingredients or [])) & set(wanted))
        claims = read('manufacturer_claims') if intent.get('benefits') or intent.get('supporting_benefits') else None
        declared = {claim['concept'] for claim in claims or []}
        benefit_hits = sorted(declared & set(intent.get('benefits', [])))
        supporting_hits = sorted(declared & set(intent.get('supporting_benefits', [])))
        finish = read('finish') if intent.get('finishes') else None
        finish_hits = [finish] if finish in intent.get('finishes', []) else []
        occasion = read('occasions') if intent['kind'] == 'occasion' else None
        occasion_hit = intent.get('occasion') in (occasion or [])
        kind = intent['kind']
        state = 'insufficient_evidence'
        if contradictions:
            state = 'no_fit'
        elif None in (category_ok, area_ok, form_ok, subcategory_ok) or market is None:
            state = 'insufficient_evidence'
        elif kind == 'ingredient':
            if ingredient_hits:
                state = 'direct_fit'
            elif product['ingredient_completeness'] == 'complete' and ingredients is not None:
                state = 'no_fit'
                contradictions.append('Required exact ingredient absent from complete listed INCI; derivatives are not equivalent')
            else:
                missing.append('Ingredient presence cannot be established from incomplete INCI')
        elif kind == 'format':
            state = 'direct_fit'
        elif kind == 'benefit':
            if benefit_hits:
                state = 'direct_fit'
            elif supporting_hits or ingredient_hits:
                state = 'supporting_fit'
            elif claims is not None:
                state = 'no_fit'
        elif kind == 'look':
            if benefit_hits or finish_hits:
                state = 'supporting_fit'
            elif claims is not None and finish is not None:
                state = 'no_fit'
        elif kind == 'occasion':
            if occasion_hit:
                state = 'direct_fit'
            elif benefit_hits:
                state = 'supporting_fit'
                missing.append('No source-backed Deepavali occasion claim; supporting makeup attributes only')
        if product.get('requires_review') and state != 'no_fit':
            state = 'insufficient_evidence'
            missing.append('Source record quarantined pending identity/field consistency review')
        warnings = list(product['quality_warnings'])
        warnings.append('Rule-based catalogue compatibility, not efficacy, demand or purchase advice')
        if kind in ('look', 'occasion'):
            warnings.append('Look/occasion intent is a provisional editorial hypothesis, not validated consumer preference')
        # Explanations carry only literal field values and references, not generated efficacy claims.
        supporting = [ref for ref in evidence if ref['field'] in {
            'category', 'subcategory', 'market', 'application_area', 'product_format',
            'normalized_ingredients', 'manufacturer_claims', 'finish', 'occasions'}]
        return {'product_id':product['product_id'], 'product_name':product['product_name'],
                'brand':product['brand'], 'fit_state':state, 'method_version':METHOD,
                'dimensions':{'ingredient_agreement':{'requested':wanted,'matched':ingredient_hits,
                                  'completeness':product['ingredient_completeness']},
                              'declared_benefit_agreement':{'matched':benefit_hits,'supporting':supporting_hits,
                                  'claim_scope':'source_declared_not_independently_verified'},
                              'format_compatibility':{'value':form,'compatible':form_ok},
                              'application_area_compatibility':{'value':areas,'compatible':area_ok},
                              'subcategory_compatibility':{'value':subcategory,'compatible':subcategory_ok},
                              'look_agreement':{'matched':finish_hits},
                              'occasion_agreement':{'explicit_match':occasion_hit}},
                'supporting_evidence':supporting, 'missing_evidence':list(dict.fromkeys(missing)),
                'contradictions':contradictions, 'warnings':warnings,
                'provenance':{'catalogue_version':self.catalogue.version,
                              'source_ids':sorted({ref['source_id'] for ref in evidence}),
                              'product':product}}

    def topic(self, topic_id, query_id='canonical'):
        topic, query, intent = self.context(topic_id, query_id)
        assessments = [self.assess(product, intent) for product in self.catalogue.products]
        assessments.sort(key=lambda row:(FIT_ORDER[row['fit_state']], row['product_id']))
        matches = [row for row in assessments if row['fit_state'] in ('direct_fit','supporting_fit')]
        return {'topic_id':topic_id, 'canonical_topic':topic['name'], 'query_id':query_id,
                'query':query, 'market':topic['market'], 'intent':intent,
                'data_mode':'real', 'output_kind':'rule_based_catalogue_fit', 'state':'provisional',
                'method_version':METHOD, 'intent_version':self.intents['version'],
                'catalogue_version':self.catalogue.version, 'matched_products':matches,
                'assessments':assessments, 'counts':dict(Counter(row['fit_state'] for row in assessments)),
                'warnings':['Curated MY listing evidence, not live stock, price, suitability or measured commercial potential',
                            'Human Product Fit evaluation pending; aliases are assessed separately'],
                'ranking_method':'direct_fit then supporting_fit; stable product ID ties, no combined score'}

    def legacy(self, topic_id, query_id='canonical', hashtag=None):
        result = self.topic(topic_id, query_id)
        products = []
        for row in result['matched_products']:
            product = row['provenance']['product']
            products.append({'product_id':row['product_id'], 'product_name':row['product_name'],
                'category':product['subcategory'],
                'description':'; '.join(c['text'] for c in product['manufacturer_claims'] or []) or 'Claims not recorded',
                'match_reason':row['fit_state']+'; evidence: '+', '.join(sorted({e['field'] for e in row['supporting_evidence']})),
                'application_tip':None, 'price_range':None, 'availability':None,
                'humidity_suitable':None, 'fit_state':row['fit_state'], 'fit_evidence':row,
                'source_url':self.catalogue.sources[product['source_id']]['url'],
                'data_mode':'real', 'output_kind':'rule_based_catalogue_fit'})
        return {'trend_id':topic_id,'trend_name':result['canonical_topic'],
                'hashtag':'#'+(hashtag or slug(result['canonical_topic'])),
                'trend_description':'Source-backed catalogue compatibility; not a measured market opportunity.',
                'recommended_products':products, 'total_products':len(products),
                'target_audience':None,'look_style':None,'malaysia_relevance':'MY product listings; cultural fit unverified',
                'color_palette':[], 'application_tips':[], 'marketing_angles':[],
                'estimated_cost':None,'estimated_total_cost':None, 'opportunity_score':None,
                'campaign_hook':None, 'data_mode':'real','recommendation_kind':'rule_based_catalogue_fit',
                'catalogue_version':self.catalogue.version, 'warnings':result['warnings']}
