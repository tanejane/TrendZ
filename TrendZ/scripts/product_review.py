"""Loopback-only human Product Fit review; separate from the public application."""

import argparse
import hmac
import json
import secrets
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from flask import Flask, jsonify, render_template, request, Response
from services.product_review import ReviewStore, ReviewConflict
from services.product_validation import markdown_report
from services.product_review_assist import import_assists, accept


def create_app(store):
    app = Flask(__name__,template_folder=str(ROOT/'templates'),static_folder=str(ROOT/'static'))
    app.config['MAX_CONTENT_LENGTH'] = 16*1024
    token = secrets.token_urlsafe(32)

    @app.before_request
    def local_only():
        hostname = urlsplit('http://'+request.host).hostname
        if request.remote_addr not in ('127.0.0.1','::1') or hostname not in ('localhost','127.0.0.1','::1'):
            return jsonify(message='Review is available on loopback only'),403
        if request.method not in ('GET','HEAD','OPTIONS'):
            origin = request.headers.get('Origin')
            if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
                return jsonify(message='Cross-origin review writes are not allowed'),403
            if not hmac.compare_digest(request.headers.get('X-Review-Token',''),token):
                return jsonify(message='Review token required; reload this local page'),403

    @app.after_request
    def private(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.errorhandler(ReviewConflict)
    def conflict(error):
        return jsonify(message=str(error)),409

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(message=str(error)),400

    @app.errorhandler(KeyError)
    def missing(error):
        return jsonify(message=str(error.args[0])),404

    @app.errorhandler(sqlite3.Error)
    @app.errorhandler(OSError)
    def storage_error(error):
        app.logger.error('Local review storage unavailable: %s', error)
        return jsonify(message='Local review storage unavailable. Preserve the session and retry.'),503

    @app.get('/')
    def index():
        return render_template('product-review.html',review_token=token)

    @app.get('/api/review')
    def summary():
        return jsonify(store.summary())

    @app.get('/api/review/pair')
    def pair():
        identifier = request.args.get('pair_id')
        row = next((row for row in store.rows() if row['pair_id']==identifier),None)
        if row is None:
            raise KeyError('Unknown fixed review pair')
        return jsonify(row)

    @app.post('/api/review/label')
    def save():
        payload = request.get_json(silent=True)
        allowed = {'pair_id','human_label','notes','unsupported_explanation','revision','reviewer','reset'}
        if not isinstance(payload,dict) or set(payload)-allowed:
            raise ValueError('Only human label, notes, evidence judgment, reviewer and revision may be saved')
        if type(payload.get('reset',False)) is not bool:
            raise ValueError('Reset must be a boolean')
        result = store.save(payload.get('pair_id'),payload.get('human_label'),payload.get('notes',''),
                            payload.get('unsupported_explanation'),payload.get('revision'),
                            payload.get('reviewer'),payload.get('reset',False))
        return jsonify(saved=result,progress=store.summary())

    @app.get('/api/review/export')
    def export():
        return Response(json.dumps(store.export(),indent=2),mimetype='application/json',
                        headers={'Content-Disposition':'attachment; filename=product-fit-human-review.json'})

    @app.post('/api/review/accept-assist')
    def accept_assist():
        payload = request.get_json(silent=True)
        if not isinstance(payload,dict) or set(payload)-{'approvals','topic_id','reviewer'}:
            raise ValueError('Only approvals, topic ID and reviewer may be submitted')
        result = accept(store,payload.get('approvals'),payload.get('topic_id'),payload.get('reviewer'))
        return jsonify(result=result,progress=store.summary())

    @app.get('/api/review/report')
    def report_status():
        # A GET never finalizes or writes a validation report.
        progress = store.summary()
        return jsonify(state='ready' if progress['ready'] else 'pending',progress=progress,
                       message='Generate a validation report only after all labels and explanation checks are complete')

    @app.post('/api/review/finalize')
    def finalize():
        report = store.finalized_report()
        return jsonify(report),200 if report['state']=='complete' else 409

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['serve','status','export','report','assist-import'])
    parser.add_argument('--db',type=Path,default=ROOT/'data/products/review_sessions/local.sqlite3')
    parser.add_argument('--port',type=int,default=5015)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/phase4c')
    parser.add_argument('--prescreen',type=Path)
    parser.add_argument('--research',type=Path)
    parser.add_argument('--apply',action='store_true',help='Import assistance only; never accept human labels')
    args = parser.parse_args()
    store = ReviewStore(args.db)
    if args.command=='serve':
        store.initialize()
        create_app(store).run(host='127.0.0.1',port=args.port,debug=False)
    else:
        if not args.db.exists():
            parser.error('Start serve once to create the fixed local review session')
        if args.command=='assist-import':
            if not args.prescreen or not args.research:
                parser.error('assist-import requires --prescreen and --research')
            print(json.dumps(import_assists(store,args.prescreen,args.research,args.apply),indent=2))
        elif args.command=='status':
            print(json.dumps({key:value for key,value in store.summary().items() if key!='pairs'},indent=2))
        elif args.command=='export':
            args.output.mkdir(parents=True,exist_ok=True)
            target = args.output/'human_review_export.json'
            # A timestamped session DB remains the authoritative event/revision history.
            target.write_text(json.dumps(store.export(),indent=2)+'\n',encoding='utf-8')
            print(target)
        elif args.command=='report':
            report = store.finalized_report()
            if report['state']!='complete':
                print(json.dumps(report,indent=2))
                return 1
            args.output.mkdir(parents=True,exist_ok=True)
            name = 'validation-'+report['session_id']+'-'+report['revision_hash'][:12]
            for suffix,content in [('json',json.dumps(report,indent=2)+'\n'),('md',markdown_report(report))]:
                path = args.output/(name+'.'+suffix)
                path.write_text(content,encoding='utf-8')
                print(path)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
