"""Export read-only Product Fit examples and evaluate a fixed human review file."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.product_fit import ProductFit, METHOD
from services.product_evaluation import evaluate


def create_review(service):
    rows = []
    for topic in service.intents['topics']:
        for assessment in service.topic(topic)['assessments']:
            product = assessment['provenance']['product']
            split = 'dev' if int(hashlib.sha256(product['family_id'].encode()).hexdigest(),16)%3==0 else 'evaluation'
            rows.append({'topic_id':topic,'query_id':'canonical','product_id':product['product_id'],
                         'family_id':product['family_id'],'split':split,
                         'sampling_stratum_machine_only':assessment['fit_state'],
                         'human_label':None,'reviewer':None,'reviewed_on':None,
                         'unsupported_explanation':None,'notes':None})
    return {'catalogue_version':service.catalogue.version,'method_version':METHOD,
            'instructions':'Human labels only. Inspect source and intent. Machine sampling strata are not gold labels. Do not move families between splits.',
            'label_choices':['direct_fit','supporting_fit','no_fit','insufficient_evidence'],
            'rows':rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/phase4b')
    parser.add_argument('--review',type=Path,default=ROOT/'data/products/human_review.json')
    parser.add_argument('--initialize-review',action='store_true')
    args = parser.parse_args()
    service = ProductFit()
    if args.initialize_review:
        if args.review.exists():
            raise ValueError('Refusing to overwrite human review edits')
        args.review.write_text(json.dumps(create_review(service),indent=2)+'\n',encoding='utf-8')
    review = json.loads(args.review.read_text(encoding='utf-8'))
    args.output.mkdir(parents=True,exist_ok=True)
    examples = {topic:service.topic(topic) for topic in service.intents['topics']}
    # Full pair-level responses retain exact catalogue fields and references for review.
    (args.output/'examples.json').write_text(json.dumps(examples,indent=2)+'\n',encoding='utf-8')
    report = evaluate(service,review)
    report['topic_counts'] = {topic:data['counts'] for topic,data in examples.items()}
    (args.output/'evaluation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'products':len(service.catalogue.products),'topics':report['topic_counts'],
                      'human_labels':sum(row['human_label'] is not None for row in review['rows'])},indent=2))


if __name__ == '__main__':
    main()
