"""Read-only protected/source audit; writes only its own readiness report."""
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def main():
    output=ROOT/'reports/phase8a'
    baseline=json.loads((output/'protected_baseline.json').read_text(encoding='utf-8-sig'))
    hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in baseline}
    if hashes!=baseline: raise ValueError('Protected evidence or code changed.')
    patterns={'openai_style_key':re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{30,}'),
              'google_style_key':re.compile(r'\bAIza[0-9A-Za-z_-]{30,}'),
              'private_key_header':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')}
    findings=[]; scanned=0; legacy_html=[]
    for directory in ('services','scripts','templates','static','tests'):
        for path in (ROOT/directory).rglob('*'):
            if path.suffix not in ('.py','.js','.cjs','.html','.css') or '__pycache__' in path.parts: continue
            content=path.read_text(encoding='utf-8-sig');scanned+=1
            if 'innerHTML' in content and directory in ('templates','static'):
                legacy_html.append(str(path.relative_to(ROOT)).replace('\\','/'))
            for kind,pattern in patterns.items():
                if pattern.search(content):findings.append({'path':str(path.relative_to(ROOT)),'kind':kind})
    broken=[]
    for path in [ROOT/'README.md',*(ROOT/'portfolio').glob('*.md')]:
        for link in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
            if link.startswith(('http:','https:','#')):continue
            if not (path.parent/link.split('#')[0]).exists():broken.append({'document':str(path.relative_to(ROOT)),'link':link})
    result={'protected_files':len(hashes),'protected_unchanged':True,'before':baseline,'after':hashes,
            'source_files_scanned':scanned,'secret_pattern_findings':findings,
            'secret_scan_scope':'Source-only known-format heuristic; no credential files read, no guarantee of absence of every secret format.',
            'broken_current_document_links':broken,'legacy_html_interpolation_files':legacy_html,
            'legacy_policy':'Kept for reproducibility; measured dashboard/watchlist and current evidence/scenario views use safe DOM rendering. Original product browser escapes values. Remaining demo templates are not production-hardened.',
            'production_ready':False,'local_demo_with_frozen_assets':True}
    (output/'technical_audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('before','after')},indent=2))
    if findings or broken:raise SystemExit(1)


if __name__=='__main__':main()
