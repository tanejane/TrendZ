"""Loopback-only creator profile/affinity review, isolated from Product Fit and producer data."""
import argparse
import hmac
import json
import secrets
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from flask import Flask, Response, jsonify, render_template, request
from services.creator_review import CreatorReviewStore, CreatorReviewConflict
from services.creator_review_evaluation import markdown_report


def create_app(store):
    app=Flask(__name__,template_folder=str(ROOT/'templates'),static_folder=str(ROOT/'static'))
    app.config['MAX_CONTENT_LENGTH']=32*1024
    token=secrets.token_urlsafe(32)

    @app.before_request
    def local_only():
        host=urlsplit('http://'+request.host).hostname
        if request.remote_addr not in ('127.0.0.1','::1') or host not in ('localhost','127.0.0.1','::1'):
            return jsonify(message='Loopback-only review workspace'),403
        if request.method not in ('GET','HEAD','OPTIONS'):
            origin=request.headers.get('Origin')
            if origin and origin.rstrip('/')!=request.host_url.rstrip('/'):
                return jsonify(message='Cross-origin writes rejected'),403
            if not hmac.compare_digest(request.headers.get('X-Review-Token',''),token):
                return jsonify(message='Review token required; reload the page'),403

    @app.after_request
    def private(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https://i.ytimg.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.errorhandler(CreatorReviewConflict)
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
    def unavailable(error):
        app.logger.error('Creator review storage error: %s',error)
        return jsonify(message='Review storage unavailable; preserve the session and retry'),503

    @app.get('/')
    def index():
        return render_template('creator-review.html',review_token=token)

    @app.get('/api/review')
    def summary():
        return jsonify(store.summary())

    @app.get('/api/review/unit')
    def unit():
        return jsonify(store.record(request.args.get('unit_id')))

    @app.get('/api/review/history')
    def history():
        return jsonify(events=store.history(request.args.get('unit_id')))

    @app.post('/api/review/save')
    def save():
        result=store.save(request.get_json(silent=True))
        return jsonify(saved=result)

    @app.get('/api/review/export/<kind>')
    def export(kind):
        if kind not in ('profile','affinity'):
            raise KeyError('Unknown review unit type')
        return Response(json.dumps(store.export(kind),indent=2),mimetype='application/json',
            headers={'Content-Disposition':'attachment; filename=creator-'+kind+'-review.json'})

    @app.get('/api/review/evaluation')
    def evaluation_status():
        summary=store.summary()
        return jsonify(state='ready' if summary['ready'] else 'pending',progress=summary,
                       reason='Final validation requires explicit completion of both review units')

    @app.post('/api/review/evaluate')
    def evaluate():
        report=store.finalize()
        return jsonify(report),200 if report['state']=='complete' else 409

    return app


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['serve','prepare','status','export','evaluate'])
    parser.add_argument('--source',type=Path,default=ROOT/'reports/phase5b/live-initial/review_dataset.json')
    parser.add_argument('--db',type=Path,default=ROOT/'data/creators/review_sessions/local.sqlite3')
    parser.add_argument('--output',type=Path,default=ROOT/'reports/phase5c')
    parser.add_argument('--port',type=int,default=5016)
    args=parser.parse_args()
    store=CreatorReviewStore(args.db)
    if args.command in ('prepare','serve'):
        store.initialize(args.source)
    elif not args.db.exists():
        parser.error('Run prepare or serve to initialize the fixed review session')
    if args.command=='serve':
        create_app(store).run(host='127.0.0.1',port=args.port,debug=False,use_reloader=False)
    elif args.command in ('prepare','export'):
        args.output.mkdir(parents=True,exist_ok=True)
        for kind in ('profile','affinity'):
            path=args.output/('creator_'+kind+'_review'+('' if args.command=='prepare' else '_export')+'.json')
            content=json.dumps(store.export(kind),indent=2)+'\n'
            if path.exists() and path.read_text(encoding='utf-8')!=content:
                raise CreatorReviewConflict('Refusing to overwrite a different review dataset; use a new --output directory')
            path.write_text(content,encoding='utf-8')
        summary=store.summary()
        print(json.dumps({'session_id':summary['session']['session_id'],'source_sha256':summary['session']['source_sha256'],
                          **{key:summary[key] for key in ('by_type','by_group','ready')}},indent=2))
    elif args.command=='status':
        summary=store.summary()
        print(json.dumps({'session_id':summary['session']['session_id'],
                          **{key:summary[key] for key in ('by_type','by_group','ready')}},indent=2))
    else:
        report=store.finalize()
        if report['state']!='complete':
            print(json.dumps({'state':'pending','reason':report['reason']},indent=2))
            return 1
        args.output.mkdir(parents=True,exist_ok=True)
        path=args.output/('validation-'+report['review_revision_hash'][:16]+'.json')
        content=json.dumps(report,indent=2)+'\n'
        if path.exists() and path.read_text(encoding='utf-8')!=content:
            raise CreatorReviewConflict('Refusing to overwrite a different final evaluation report')
        path.write_text(content,encoding='utf-8')
        path.with_suffix('.md').write_text(markdown_report(report),encoding='utf-8')
        print(path)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
