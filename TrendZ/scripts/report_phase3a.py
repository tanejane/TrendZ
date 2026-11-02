"""Export actual read-only API responses for the eight pilot topics. No ingestion."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app_backend


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'reports/phase2-measured/pilot.sqlite3')
    parser.add_argument('--output',type=Path,default=ROOT/'reports/phase3a')
    args = parser.parse_args()
    if not args.db.exists():
        parser.error('Measured database does not exist; no example data will be invented')
    before = hashlib.sha256(args.db.read_bytes()).hexdigest()
    config = json.loads((ROOT/'data/pilot_phase2.json').read_text(encoding='utf-8'))
    app_backend.app.config.update(TESTING=True,DATABASE_PATH=str(args.db))
    responses = {}
    with app_backend.app.test_client() as client:
        for identifier in config['topic_ids']:
            response = client.get('/api/intelligence/'+identifier)
            if response.status_code!=200:
                raise RuntimeError('Example API request failed: '+identifier)
            responses[identifier] = response.get_json()
    after = hashlib.sha256(args.db.read_bytes()).hexdigest()
    if before!=after:
        raise RuntimeError('Read-only report changed the source database')
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'responses.json').write_text(json.dumps(responses,indent=2),encoding='utf-8')
    names = list(next(iter(responses.values()))['dimensions'])
    states = {topic:{name:payload['dimensions'][name]['state'] for name in names} for topic,payload in responses.items()}
    (args.output/'states.json').write_text(json.dumps(states,indent=2),encoding='utf-8')
    lines = ['# Phase 3A Measured API Examples','',
             'Actual canonical-query responses from the measured pilot database. Source database was not modified.',
             'Human relevance remains deferred. Available means supported at the response scope, not validated topic intelligence.',
             '', '| Topic | '+' | '.join(names)+' |', '| --- | '+' | '.join(['---']*len(names))+' |']
    for topic,values in states.items():
        lines.append('| '+topic+' | '+' | '.join(values[name] for name in names)+' |')
    lines += ['', 'Full payloads, including values, warnings, formulas, windows and provenance IDs: `responses.json`.',
              'No combined score, lifecycle classification, recommendations or commercial changes.']
    (args.output/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(args.output),'database_unchanged':before==after,'states':states},indent=2))


if __name__=='__main__':
    main()
