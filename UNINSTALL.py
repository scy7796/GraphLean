#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, re, secrets, shutil, sys
from pathlib import Path
VERSION='1.0.0'; MARK_BEGIN='# GRAPHLEAN_V1_0_0_BEGIN'; MARK_END='# GRAPHLEAN_V1_0_0_END'; META_NAME='.graphlean-installer-v1.0.0'
BACKUP_ID=re.compile(r'^\d{8}T\d{6}\.\d{6}Z-[0-9a-f]{8}$')

def file_sha(p: Path): h=hashlib.sha256(); h.update(p.read_bytes()); return h.hexdigest()
def home_fingerprint(home: Path): return hashlib.sha256(str(home).encode('utf-8')).hexdigest()
def tree_fingerprint(root: Path):
 rows=[]
 for p in sorted(root.rglob('*'),key=lambda x:x.relative_to(root).as_posix()):
  rel=p.relative_to(root).as_posix()
  if p.is_symlink(): rows.append(f'L {rel} {os.readlink(p)}')
  elif p.is_dir(): rows.append(f'D {rel}')
  elif p.is_file(): rows.append(f'F {rel} {file_sha(p)}')
  else: raise RuntimeError(f'unsupported filesystem entry in backup: {p}')
 return hashlib.sha256(('\n'.join(rows)+'\n').encode('utf-8')).hexdigest()
def safe_manifest_rel(rel: str):
 if not isinstance(rel,str) or not rel or '\\' in rel: return False
 p=Path(rel)
 return not p.is_absolute() and '..' not in p.parts and '.' not in p.parts
def marker_block(): return f"{MARK_BEGIN}\n- insert:\n    - id: graphlean-gate\n      name: './graphlean/plugin/index.js'\n{MARK_END}\n"
def copytree(src: Path,dst: Path): shutil.copytree(src,dst,symlinks=True)
def strip_marker(text: str):
 if text.count(MARK_BEGIN)>1 or text.count(MARK_END)>1: raise RuntimeError('duplicate GraphLean markers: refusing destructive edit')
 a=text.find(MARK_BEGIN); b=text.find(MARK_END)
 if a<0 and b<0:return text,False
 if a<0 or b<0 or b<a: raise RuntimeError('partial GraphLean marker: refusing destructive edit')
 end=b+len(MARK_END)
 if end<len(text) and text[end]=='\n': end+=1
 if text[a:end].rstrip('\n') != marker_block().rstrip('\n'): raise RuntimeError('GraphLean marker block was modified; refusing destructive edit')
 new=text[:a]+text[end:]
 return ('[]\n' if new.strip()=='' else new.rstrip()+'\n'),True

def load_manifest(manifest: Path, home: Path):
 d=json.loads(manifest.read_text(encoding='utf-8'))
 required={'schemaVersion','version','homeFingerprint','backupId','hadPatchPreimage','hadPluginPreimage','hadStatePreimage','preimages','files'}
 if not isinstance(d,dict) or set(d)!=required or d.get('schemaVersion')!=4 or d.get('version')!=VERSION: raise RuntimeError('invalid install manifest schema/version')
 if d.get('homeFingerprint')!=home_fingerprint(home): raise RuntimeError('install manifest is not bound to this DSH_HOME')
 if not isinstance(d.get('backupId'),str) or not BACKUP_ID.fullmatch(d['backupId']): raise RuntimeError('invalid backup id')
 for k in ('hadPatchPreimage','hadPluginPreimage','hadStatePreimage'):
  if not isinstance(d.get(k),bool): raise RuntimeError(f'invalid install manifest field {k}')
 pre=d.get('preimages')
 if not isinstance(pre,dict) or set(pre)!={'patch','plugin','state'}: raise RuntimeError('invalid preimage fingerprints')
 for name,flag in (('patch',d['hadPatchPreimage']),('plugin',d['hadPluginPreimage']),('state',d['hadStatePreimage'])):
  value=pre.get(name)
  if flag and (not isinstance(value,str) or not re.fullmatch(r'[0-9a-f]{64}',value)): raise RuntimeError(f'invalid {name} preimage fingerprint')
  if not flag and value is not None: raise RuntimeError(f'unexpected {name} preimage fingerprint')
 if not isinstance(d.get('files'),dict) or any(not safe_manifest_rel(rel) or not isinstance(h,str) or not re.fullmatch(r'[0-9a-f]{64}',h) for rel,h in d.get('files',{}).items()): raise RuntimeError('invalid install manifest files')
 return d

def package_drift(plugin: Path, expected: dict):
 if not plugin.is_dir() or plugin.is_symlink(): return ['<plugin missing/not regular directory>']
 unsafe=[str(p.relative_to(plugin)).replace('\\','/') for p in plugin.rglob('*') if p.is_symlink()]
 actual={str(p.relative_to(plugin)).replace('\\','/'):file_sha(p) for p in plugin.rglob('*') if p.is_file() and not p.is_symlink()}
 drift=list(unsafe); drift.extend(rel for rel,want in expected.items() if actual.get(rel)!=want); drift.extend(sorted(set(actual)-set(expected)))
 return sorted(set(drift))

def validate_preimages(backup: Path,d: dict):
 if not backup.is_dir() or backup.is_symlink(): raise RuntimeError('bound backup directory missing or unsafe')
 checks=(('hadPluginPreimage','plugin-preimage',True,'plugin'),('hadStatePreimage','state-preimage',True,'state'),('hadPatchPreimage','cordis.patch.yml',False,'patch'))
 for flag,name,is_dir,key in checks:
  if d[flag]:
   p=backup/name
   if p.is_symlink() or (is_dir and not p.is_dir()) or (not is_dir and not p.is_file()): raise RuntimeError(f'bound backup preimage missing/unsafe: {name}')
   got=tree_fingerprint(p) if is_dir else file_sha(p)
   if got!=d['preimages'][key]: raise RuntimeError(f'bound backup preimage fingerprint mismatch: {name}')

def stage_preimage(meta: Path,backup: Path,d: dict):
 staged=meta/f'.restore-{os.getpid()}-{secrets.token_hex(4)}'; staged.mkdir()
 try:
  if d['hadPluginPreimage']: copytree(backup/'plugin-preimage',staged/'plugin')
  if d['hadStatePreimage']: copytree(backup/'state-preimage',staged/'state')
  return staged
 except Exception:
  shutil.rmtree(staged,ignore_errors=True)
  raise

def cleanup_metadata(meta: Path,backup: Path,manifest: Path):
 if manifest.exists(): manifest.unlink()
 if backup.exists(): shutil.rmtree(backup,ignore_errors=True)
 backups=meta/'backups'
 if backups.is_dir() and not any(backups.iterdir()): backups.rmdir()
 if meta.is_dir() and not any(meta.iterdir()): meta.rmdir()

def main(argv=None):
 ap=argparse.ArgumentParser(); ap.add_argument('--dsh-home',default=os.environ.get('DSH_HOME') or str(Path.home()/'.dsh')); ap.add_argument('--restore-backup',action='store_true'); args=ap.parse_args(argv)
 home=Path(args.dsh_home).expanduser().resolve(); meta=home/META_NAME; manifest=meta/'install.json'; graph_root=home/'graphlean'; plugin=graph_root/'plugin'; state=graph_root/'state'; patch=home/'cordis.patch.yml'
 if patch.is_symlink(): raise RuntimeError('unsafe symlinked cordis.patch.yml; refusing destructive action')
 if not manifest.is_file(): raise RuntimeError(f'install manifest not found: {manifest}')
 if graph_root.is_symlink() or plugin.is_symlink() or state.is_symlink(): raise RuntimeError('unsafe symlink in GraphLean managed paths; refusing destructive action')
 d=load_manifest(manifest,home); backup=meta/'backups'/d['backupId']; validate_preimages(backup,d)
 current_patch=patch.read_text(encoding='utf-8') if patch.is_file() else None
 if not args.restore_backup:
  drift=package_drift(plugin,d['files'])
  if drift: raise RuntimeError('installed GraphLean plugin drift detected; no uninstall changes were made. Review changes or use --restore-backup to explicitly discard them: '+', '.join(drift[:20]))
  if current_patch is None: raise RuntimeError('DSH patch file missing; no uninstall changes were made')
  new_patch,changed=strip_marker(current_patch)
  if not changed: raise RuntimeError('GraphLean patch marker missing; no uninstall changes were made')
 else:
  if d['hadPatchPreimage']: new_patch=(backup/'cordis.patch.yml').read_text(encoding='utf-8')
  else: new_patch=None

 staged=stage_preimage(meta,backup,d)
 tomb_plugin=meta/f'.remove-plugin-{os.getpid()}-{secrets.token_hex(3)}'; tomb_state=meta/f'.remove-state-{os.getpid()}-{secrets.token_hex(3)}'
 moved_plugin=moved_state=False
 try:
  if plugin.exists(): os.replace(plugin,tomb_plugin); moved_plugin=True
  if state.exists(): os.replace(state,tomb_state); moved_state=True
  if (staged/'plugin').exists(): plugin.parent.mkdir(parents=True,exist_ok=True); os.replace(staged/'plugin',plugin)
  if (staged/'state').exists(): state.parent.mkdir(parents=True,exist_ok=True); os.replace(staged/'state',state)
  if new_patch is None:
   if patch.exists(): patch.unlink()
  else:
   tmp=patch.with_name(patch.name+f'.tmp-{os.getpid()}'); tmp.write_text(new_patch,encoding='utf-8'); os.replace(tmp,patch)
 except Exception:
  try:
   if plugin.exists(): shutil.rmtree(plugin,ignore_errors=True)
   if state.exists(): shutil.rmtree(state,ignore_errors=True)
   if moved_plugin and tomb_plugin.exists(): os.replace(tomb_plugin,plugin)
   if moved_state and tomb_state.exists(): os.replace(tomb_state,state)
   if current_patch is None:
    if patch.exists(): patch.unlink()
   else:
    tmp=patch.with_name(patch.name+f'.rollback-{os.getpid()}'); tmp.write_text(current_patch,encoding='utf-8'); os.replace(tmp,patch)
  except Exception as rollback_error: print(f'CRITICAL: uninstall rollback failed: {rollback_error}',file=sys.stderr)
  raise
 finally:
  if staged.exists(): shutil.rmtree(staged,ignore_errors=True)
 if tomb_plugin.exists(): shutil.rmtree(tomb_plugin,ignore_errors=True)
 if tomb_state.exists(): shutil.rmtree(tomb_state,ignore_errors=True)
 cleanup_metadata(meta,backup,manifest)
 if graph_root.is_dir() and not any(graph_root.iterdir()): graph_root.rmdir()
 print('RESTORED exact pre-install GraphLean plugin/state/patch snapshot' if args.restore_backup else 'UNINSTALLED GraphLean; unrelated patch edits preserved and pre-install plugin/state restored')
 return 0
if __name__=='__main__':
 try: raise SystemExit(main())
 except Exception as e: print(f'ERROR: {e}',file=sys.stderr); raise SystemExit(2)

