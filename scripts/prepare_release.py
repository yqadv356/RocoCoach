"""Create an explicit, scanned reviewer package without touching private history."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
DOCS=['gameplay-cover.png','VALIDATION.md','DELIVERY_STATUS.md','lolo-ui-evidence.json','lolo-layout-preview.png','lolo-checking-preview.png','lolo-speaking-preview.png','lolo-failure-preview.png','lolo-review-stable-preview.png','MASCOT_DESIGN.md','lolo-states-preview.png','lolo-companion-preview.png','SUBMISSION_DRAFT.md','REVIEWER_GUIDE.md','AGENT_EXECUTION_DESIGN.md','RAG_IMPLEMENTATION.md',
      'SHORT_MATCH_RESOURCES.md','RESPONSE_LIFECYCLE.md','ASYNC_REVIEW.md','PUBLIC_BUILD_LOG.md',
      'semantic-agent-execution-preview.png','semantic-actions-live-evidence.json',
      'semantic-intent-probe-evidence.json','semantic-intent-probe-normalized-evidence.json',
      'active-replacement-check-evidence.json','rag-evaluation.json','rag-evaluation-final.json',
      'async-review-prefetch-json-live-evidence.json']
DATA=['rag_eval.json','conversation_review.json','zh_catalog.json','agent_intent_eval.json','rag_corpus.json','coach_knowledge.json']
DOCS += ['README.md','DELIVERY_GUIDE.md','INTERVIEW_PLAYBOOK.md','INTERVIEW_NOTES.md','RULES_AND_CONTEXT.md',
         'FULL_MATCH_DESIGN.md','MATCH_TOOLS.md','FINAL_ACCEPTANCE.md',
         'final-semantic-actions-evidence.json','final-match-tools-evidence.json',
         'final-async-review-evidence.json','final-chat-style-evidence.json']
SCRIPTS=['demo_battle.py','setup_battle.py','build_knowledge.py','evaluate_rag.py','evaluate_semantic_intent.py',
         'check_challenge_actions.py','check_llm.py','check_match_tools.py','check_async_review.py','build_interview_draft.py','prepare_release.py']


def release_files(root=ROOT):
    paths=[root/p for p in ['README.md','THIRD_PARTY.md','app.py','pyproject.toml','requirements.txt','uv.lock','.python-version','.env.example','.gitignore']]
    for folder,pattern in [('rococoach','*.py'),('pages','*.py'),('tests','*.py'),('assets','*'),('docs/licenses','*'),('.vscode','*.json'),('.streamlit','config.toml'),('.github/workflows','*.yml')]:
        paths.extend(p for p in (root/folder).rglob(pattern) if p.is_file() and '__pycache__' not in p.parts and p.name!='.DS_Store')
    paths.extend(root/'docs'/p for p in DOCS)
    paths.extend(root/'data'/p for p in DATA)
    paths.extend(root/'scripts'/p for p in SCRIPTS)
    paths.extend(root/'engine'/p for p in ['bridge.cjs','export_knowledge.cjs','package.json','pnpm-lock.yaml'])
    return sorted(set(paths))


def scan_files(paths,secrets):
    issues=[]
    for path in paths:
        if path.is_symlink():issues.append((path.name,'symlink'));continue
        if not path.is_file():issues.append((path.name,'missing'));continue
        if path.name=='.env' or path.suffix in {'.db','.sqlite3'} or any(path.parts[i:i+2]==('data','private') for i in range(len(path.parts)-1)):
            issues.append((path.name,'private path'));continue
        blobs=[path.read_bytes()]
        if path.suffix=='.docx':
            with zipfile.ZipFile(path) as z:blobs.extend(z.read(n) for n in z.namelist() if n.endswith('.xml'))
        for blob in blobs:
            if any(value.encode() in blob for value in secrets if len(value)>10):issues.append((path.name,'local secret match'))
            if re.search(rb'(?:gh[pousr]_[A-Za-z0-9]{24,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9]{24,})',blob):issues.append((path.name,'credential-like token'))
            if re.search(rb'/Users/[A-Za-z0-9_.-]+/',blob):issues.append((path.name,'personal absolute path'))
    return sorted(set(issues))


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    target=a.output.resolve()
    if target.exists():raise SystemExit('Refusing to overwrite an existing output folder.')
    selected=release_files()
    artifact_dir=ROOT/'output/submission'
    if not artifact_dir.exists():artifact_dir=ROOT/'submission'
    docs=list(artifact_dir.glob('*.docx'))+list(artifact_dir.glob('*.pdf'))
    if len(docs)!=2:raise SystemExit('Expected one checked DOCX and one PDF in output/submission.')
    local=dotenv_values(ROOT/'.env')
    secrets=[str(v) for k,v in local.items() if v and any(t in k.upper() for t in ['KEY','TOKEN','SECRET','PASSWORD'])]
    issues=scan_files(selected+docs,secrets)
    if issues:raise SystemExit(json.dumps({'status':'blocked','issues':issues},ensure_ascii=False))
    target.mkdir(parents=True)
    for source in selected:
        dest=target/source.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    for source in docs:
        dest=target/'submission'/source.name;dest.parent.mkdir(exist_ok=True);shutil.copy2(source,dest)
    manifest={'scope':'Explicit allowlist; excludes local .env, private database, old personal screenshots and local diagnostics.',
              'scan':'Local configured secret exact-match, token patterns, personal absolute paths, no symlinks; not a security certification.',
              'files':[{ 'path':str(f.relative_to(target)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in sorted(target.rglob('*')) if f.is_file()]}
    (target/'PUBLIC_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps({'status':'prepared','files':len(manifest['files']),'output':str(target)},ensure_ascii=False))

if __name__=='__main__':main()
