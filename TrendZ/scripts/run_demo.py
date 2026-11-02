"""Serve stored measured evidence locally, using a disposable database copy."""
import argparse
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=5000)
    args=parser.parse_args()
    if not 1024<=args.port<=65535: parser.error('Choose a port between 1024 and 65535.')
    evidence=ROOT/'reports/phase2-measured/pilot.sqlite3'
    from services.creator_candidates import CreatorCandidates
    try:
        CreatorCandidates(ROOT)
        if not evidence.is_file(): raise FileNotFoundError()
    except (OSError,ValueError):
        parser.error('Frozen demo evidence is missing/invalid. See README Local Setup; no synthetic fallback was used.')
    with tempfile.TemporaryDirectory(prefix='trendz-demo-') as directory:
        target=Path(directory)/'demo.sqlite3'
        with sqlite3.connect(evidence.as_uri()+'?mode=ro',uri=True) as source:
            with sqlite3.connect(target) as copy: source.backup(copy)
        os.environ['TRENDZ_DATA_MODE']='real'
        os.environ['TRENDZ_DB_PATH']=str(target)
        from app_backend import app
        print('Stored measured snapshot. No live collection or LLM provider. Watchlist changes are temporary.',flush=True)
        app.run(host='127.0.0.1',port=args.port,debug=False,use_reloader=False)


if __name__=='__main__': main()
