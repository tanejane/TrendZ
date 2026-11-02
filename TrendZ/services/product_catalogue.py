"""Read-only, versioned catalogue. Source claims are not efficacy measurements."""

import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('brand', 'product_name', 'market', 'category', 'subcategory', 'product_format',
          'application_area', 'finish', 'raw_ingredients', 'normalized_ingredients',
          'variant', 'shade', 'size', 'manufacturer_claims', 'occasions')
INGREDIENT_ALIASES = {'nicotinamide': 'niacinamide', 'vitamin b3': 'niacinamide',
                      'vitamin b5': 'panthenol', 'aqua / water': 'water'}


def normalize_ingredient(value):
    value = re.sub(r'\s+', ' ', value.strip().lower())
    return INGREDIENT_ALIASES.get(value, value)


class Catalogue:
    def __init__(self, path=None):
        self.path = Path(path) if path else ROOT/'data/products/catalogue.json'
        self.document = json.loads(self.path.read_text(encoding='utf-8'))
        self.version = self.document['catalogue_version']
        self.sources = self.document['sources']
        self.products = self.document['products']
        ids = [p['product_id'] for p in self.products]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate product ID')
        for product in self.products:
            if product['catalogue_version'] != self.version:
                raise ValueError('Catalogue version mismatch')
            for field in FIELDS:
                if field not in product or field not in product['field_quality']:
                    raise ValueError('Missing catalogue field: '+field)
                quality = product['field_quality'][field]
                if product[field] is not None and not quality.get('evidence'):
                    raise ValueError('Unprovenanced field: '+field)
                for evidence in quality.get('evidence', []):
                    source = self.sources[evidence['source_id']]
                    if not evidence.get('basis') or urlparse(source['url']).scheme != 'https':
                        raise ValueError('Invalid field evidence')

    def evidence(self, product, field):
        quality = product['field_quality'][field]
        if quality['state'] not in ('verified', 'partial'):
            return []
        return [{'product_id':product['product_id'], 'field':field,
                 'value':product[field], 'field_state':quality['state'],
                 'catalogue_version':self.version, **entry,
                 'source':self.sources[entry['source_id']]}
                for entry in quality.get('evidence', [])]
