#!/usr/bin/env python3
from __future__ import annotations
import sys
sys.dont_write_bytecode=True
import argparse, datetime as dt, hashlib, json, os, secrets, shutil
from pathlib import Path

VERSION='1.0.1'; MARK_BEGIN='# GRAPHLEAN_V1_0_1_BEGIN'; MARK_END='# GRAPHLEAN_V1_0_1_END'
META_NAME='.graphlean-installer-v1.0.1'
ROOT=Path(__file__).resolve().parent

def file_sha(p: Path):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def home_fingerprint(home: Path): return hashlib.sha256(str(home).encode('utf-8')).hexdigest()
def tree_fingerprint(root: Path):
    rows=[]
    for p in sorted(root.rglob('*'),key=lambda x:x.relative_to(root).as_posix()):
        rel=p.relative_to(root).as_posix()
        if p.is_symlink(): rows.append(f'L {rel} {os.readlink(p)}')
        elif p.is_dir(): rows.append(f'D {rel}')
        elif p.is_file(): rows.append(f'F {rel} {file_sha(p)}')
        else: raise RuntimeError(f'unsupported filesystem entry in managed preimage: {p}')
    return hashlib.sha256(('\n'.join(rows)+'\n').encode('utf-8')).hexdigest()

def marker_block():
    return f"{MARK_BEGIN}\n- insert:\n    - id: graphlean-gate\n      name: './graphlean/plugin/index.js'\n{MARK_END}\n"

def validate_patch_text(text: str):
    stripped=text.strip()
    if not stripped or stripped=='[]': return []
    try:
        import yaml
        value=yaml.safe_load(text)
    except ImportError:
        raise RuntimeError('PyYAML is required to safely modify a non-empty existing cordis.patch.yml; install aborted before host changes')
    if not isinstance(value,list): raise RuntimeError('DSH home cordis.patch.yml must be a top-level YAML sequence')
    if value==[]: raise RuntimeError("non-canonical empty cordis.patch.yml; use exactly [] (comments/document wrappers around an empty sequence are refused for safe patching)")
    for op in value:
        if not isinstance(op,dict): continue
        rows=op.get('insert')
        if not isinstance(rows,list): continue
        for row in rows:
            if isinstance(row,dict) and (row.get('id')=='graphlean-gate' or row.get('name')=='./graphlean/plugin/index.js'):
                raise RuntimeError('cordis.patch.yml already contains a GraphLean-equivalent plugin entry without this installer marker')
    return value

def write_atomic(path: Path, text: str, mode=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f'.tmp-{os.getpid()}-{secrets.token_hex(3)}')
    tmp.write_text(text,encoding='utf-8')
    if mode is not None:
        try: os.chmod(tmp,mode)
        except OSError: pass
    os.replace(tmp,path)

def inject_patch(path: Path):
    text=path.read_text(encoding='utf-8') if path.exists() else '[]\n'
    if MARK_BEGIN in text or MARK_END in text: raise RuntimeError('GraphLean patch marker already exists')
    validate_patch_text(text)
    new=marker_block() if not text.strip() or text.strip()=='[]' else text.rstrip()+"\n\n"+marker_block()
    write_atomic(path,new)

def copytree(src: Path, dst: Path): shutil.copytree(src,dst,symlinks=True)

def restore_preimage(plugin: Path, state: Path, patch: Path, backup: Path, had_plugin: bool, had_state: bool, had_patch: bool):
    for target in (plugin,state):
        if target.exists() or target.is_symlink():
            if target.is_symlink(): target.unlink()
            elif target.is_dir(): shutil.rmtree(target)
            else: target.unlink()
    if had_plugin:
        src=backup/'plugin-preimage'
        if not src.is_dir(): raise RuntimeError('plugin preimage missing during rollback')
        plugin.parent.mkdir(parents=True,exist_ok=True); copytree(src,plugin)
    if had_state:
        src=backup/'state-preimage'
        if not src.is_dir(): raise RuntimeError('state preimage missing during rollback')
        state.parent.mkdir(parents=True,exist_ok=True); copytree(src,state)
    if had_patch:
        src=backup/'cordis.patch.yml'
        if not src.is_file(): raise RuntimeError('patch preimage missing during rollback')
        patch.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,patch)
    elif patch.exists(): patch.unlink()

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--dsh-home',default=os.environ.get('DSH_HOME') or str(Path.home()/'.dsh')); ap.add_argument('--probe-dsh',choices=('auto','always','never'),default='auto'); ap.add_argument('--profile',default='web'); args=ap.parse_args(argv)
    home=Path(args.dsh_home).expanduser().resolve(); patch=home/'cordis.patch.yml'; graph_root=home/'graphlean'
    plugin=graph_root/'plugin'; state=graph_root/'state'; meta=home/META_NAME; manifest=meta/'install.json'
    if graph_root.is_symlink(): raise RuntimeError('refusing to install through symlinked DSH graphlean root')
    if meta.exists(): raise RuntimeError(f'stale/existing GraphLean installer metadata exists: {meta}; resolve it before installing')
    if patch.is_symlink(): raise RuntimeError('refusing to modify symlinked cordis.patch.yml')
    if patch.exists() and not patch.is_file(): raise RuntimeError('cordis.patch.yml exists but is not a regular file')
    patch_text=patch.read_text(encoding='utf-8') if patch.exists() else '[]\n'; validate_patch_text(patch_text)
    legacy_hits=[]
    if (home/'graphweave').exists() or (home/'graphweave').is_symlink(): legacy_hits.append(str(home/'graphweave'))
    legacy_hits += [str(x) for x in sorted(home.glob('.graphweave-installer-*'))]
    if any(x in patch_text for x in ('GRAPHWEAVE_','graphweave-gate','./graphweave/plugin/index.js')): legacy_hits.append(str(patch))
    older_graphlean=[x for x in sorted(home.glob('.graphlean-installer-*')) if x.name!=META_NAME]
    legacy_hits += [str(x) for x in older_graphlean]
    if legacy_hits: raise RuntimeError('legacy/conflicting GraphWeave or GraphLean installation detected; uninstall the old release first: '+', '.join(legacy_hits))
    if MARK_BEGIN in patch_text or MARK_END in patch_text: raise RuntimeError('GraphLean patch marker already exists without matching installer metadata')
    for label,target in (('plugin',plugin),('state',state)):
        if target.is_symlink(): raise RuntimeError(f'refusing to replace symlinked GraphLean {label} path')
        if target.exists() and not target.is_dir(): raise RuntimeError(f'GraphLean {label} target exists but is not a directory')

    import graphleanctl
    has_manifest=(ROOT/'MANIFEST.json').is_file(); has_checksums=(ROOT/'CHECKSUMS.sha256').is_file()
    if has_manifest != has_checksums: raise RuntimeError('partial release integrity metadata; install aborted before host changes')
    source_tree=not has_manifest
    if graphleanctl.cmd_selftest(ROOT, source_tree=source_tree): raise RuntimeError('package selftest failed; DSH was not modified')

    backup_id=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'-'+secrets.token_hex(4)
    backup=meta/'backups'/backup_id
    had_patch=patch.is_file(); had_plugin=plugin.is_dir(); had_state=state.is_dir()
    preimages={'patch':file_sha(patch) if had_patch else None,'plugin':tree_fingerprint(plugin) if had_plugin else None,'state':tree_fingerprint(state) if had_state else None}
    try:
        backup.mkdir(parents=True,exist_ok=False)
        try:
            os.chmod(meta,0o700); os.chmod(meta/'backups',0o700); os.chmod(backup,0o700)
        except OSError: pass
        if had_patch: shutil.copy2(patch,backup/'cordis.patch.yml')
        if had_plugin: copytree(plugin,backup/'plugin-preimage')
        if had_state: copytree(state,backup/'state-preimage')
        copied={'patch':file_sha(backup/'cordis.patch.yml') if had_patch else None,'plugin':tree_fingerprint(backup/'plugin-preimage') if had_plugin else None,'state':tree_fingerprint(backup/'state-preimage') if had_state else None}
        if copied!=preimages: raise RuntimeError('pre-install backup verification failed; DSH was not modified')
        staging=meta/f'.staging-{os.getpid()}-{secrets.token_hex(4)}'; staging.mkdir(parents=True,exist_ok=False)
        try: os.chmod(staging,0o700)
        except OSError: pass
        shutil.copy2(ROOT/'dsh'/'index.js',staging/'index.js'); pkg=json.loads((ROOT/'package.json').read_text(encoding='utf-8')); pkg['main']='./index.js'; pkg['exports']='./index.js'; pkg.pop('files',None); pkg.pop('dsh',None); pkg.pop('keywords',None); pkg.pop('bin',None); (staging/'package.json').write_text(json.dumps(pkg,indent=2,sort_keys=True)+'\n',encoding='utf-8'); copytree(ROOT/'graph',staging/'graph')
    except Exception:
        if meta.exists(): shutil.rmtree(meta,ignore_errors=True)
        raise
    touched=False; rollback_ok=False
    try:
        touched=True  # every destructive host mutation below this point must trigger preimage restoration
        if plugin.exists(): shutil.rmtree(plugin)
        if state.exists(): shutil.rmtree(state)
        plugin.parent.mkdir(parents=True,exist_ok=True); os.replace(staging,plugin)
        inject_patch(patch)
        files={str(p.relative_to(plugin)).replace('\\','/'):file_sha(p) for p in sorted(plugin.rglob('*')) if p.is_file()}
        data={'schemaVersion':4,'version':VERSION,'homeFingerprint':home_fingerprint(home),'backupId':backup_id,
              'hadPatchPreimage':had_patch,'hadPluginPreimage':had_plugin,'hadStatePreimage':had_state,'preimages':preimages,'files':files}
        write_atomic(manifest,json.dumps(data,indent=2,sort_keys=True)+'\n',0o600)
        import SELFTEST
        SELFTEST.installed_test(home)
        if args.probe_dsh != 'never':
            if shutil.which('dsh'):
                SELFTEST.probe_dsh(home,args.profile)
            elif args.probe_dsh == 'always':
                raise RuntimeError('dsh executable not found on PATH; real loader probe was required')
            else:
                print('NOTE dsh executable not found on PATH; installed-state validation passed, real loader probe skipped')
    except Exception:
        if touched:
            try:
                restore_preimage(plugin,state,patch,backup,had_plugin,had_state,had_patch); rollback_ok=True
            except Exception as rollback_error: print(f'CRITICAL: install rollback failed: {rollback_error}',file=sys.stderr)
        else: rollback_ok=True
        if staging.exists(): shutil.rmtree(staging,ignore_errors=True)
        if rollback_ok and meta.exists(): shutil.rmtree(meta,ignore_errors=True)
        raise

    print(f'INSTALLED GraphLean {VERSION} -> {plugin}')
    print(f'PATCHED {patch} with a DSH home-level - insert entry')
    print(f'INSTALL MANIFEST {manifest}')
    print('POST-INSTALL VALIDATION PASS. Restart DeepSeek Harness before normal use.')
    return 0
if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as e: print(f'ERROR: {e}',file=sys.stderr); raise SystemExit(2)
