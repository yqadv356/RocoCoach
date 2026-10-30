from pathlib import Path
import importlib.util

spec=importlib.util.spec_from_file_location('release',Path(__file__).resolve().parents[1]/'scripts/prepare_release.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)


def test_release_scan_blocks_secrets_paths_and_symlinks(tmp_path):
    files=[]
    for name,content in [('leak.txt','my-local-secret-value-abcdef'),('path.txt','/'.join(['','Users','example','Documents','log'])),('safe.txt','synthetic public fixture')]:
        p=tmp_path/name;p.write_text(content);files.append(p)
    alias=tmp_path/'alias';alias.symlink_to(files[-1]);files.append(alias)
    issues=release.scan_files(files,['my-local-secret-value-abcdef'])
    assert ('leak.txt','local secret match') in issues
    assert ('path.txt','personal absolute path') in issues
    assert ('alias','symlink') in issues
    assert not any(name=='safe.txt' for name,reason in issues)


def test_release_allowlist_excludes_private_db_old_screenshots_and_environment():
    paths=release.release_files();relative=[str(p.relative_to(release.ROOT)) for p in paths]
    assert 'rococoach/semantic_control.py' in relative
    assert 'scripts/demo_battle.py' in relative
    assert '.env.example' in relative and '.env' not in relative
    assert not any('data/private/' in p or 'node_modules/' in p or p.startswith('tmp/') for p in relative)
    assert 'docs/semantic-agent-execution-preview.png' in relative
    assert 'docs/qwen-live-preview.png' not in relative
    assert 'docs/ENVIRONMENT.md' not in relative
