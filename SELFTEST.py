#!/usr/bin/env python3
from __future__ import annotations
import sys
sys.dont_write_bytecode=True
import argparse, hashlib, json, os, re, shutil, subprocess
from pathlib import Path
import graphleanctl

ROOT=Path(__file__).resolve().parent
VERSION='1.0.1'; MARK_BEGIN='# GRAPHLEAN_V1_0_1_BEGIN'; MARK_END='# GRAPHLEAN_V1_0_1_END'; META_NAME='.graphlean-installer-v1.0.1'
BACKUP_ID=re.compile(r'^\d{8}T\d{6}\.\d{6}Z-[0-9a-f]{8}$')
def home_fingerprint(home: Path): return hashlib.sha256(str(home).encode('utf-8')).hexdigest()
def file_sha(p: Path): return hashlib.sha256(p.read_bytes()).hexdigest()
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

def installed_test(home: Path):
 home=home.resolve(); manifest=home/META_NAME/'install.json'; plugin=home/'graphlean'/'plugin'; patch=home/'cordis.patch.yml'
 if not manifest.is_file(): raise RuntimeError(f'install manifest missing: {manifest}')
 d=json.loads(manifest.read_text(encoding='utf-8'))
 required={'schemaVersion','version','homeFingerprint','backupId','hadPatchPreimage','hadPluginPreimage','hadStatePreimage','preimages','files'}
 if not isinstance(d,dict) or set(d)!=required or d.get('schemaVersion')!=4 or d.get('version')!=VERSION: raise RuntimeError('installed manifest schema/version mismatch')
 if d.get('homeFingerprint')!=home_fingerprint(home): raise RuntimeError('installed manifest not bound to target DSH_HOME')
 if not isinstance(d.get('backupId'),str) or not BACKUP_ID.fullmatch(d['backupId']): raise RuntimeError('invalid installed backup id')
 for k in ('hadPatchPreimage','hadPluginPreimage','hadStatePreimage'):
  if not isinstance(d.get(k),bool): raise RuntimeError(f'invalid installed manifest field {k}')
 pre=d.get('preimages')
 if not isinstance(pre,dict) or set(pre)!={'patch','plugin','state'}: raise RuntimeError('invalid installed preimage fingerprints')
 for name,flag in (('patch',d['hadPatchPreimage']),('plugin',d['hadPluginPreimage']),('state',d['hadStatePreimage'])):
  value=pre.get(name)
  if flag and (not isinstance(value,str) or not re.fullmatch(r'[0-9a-f]{64}',value)): raise RuntimeError(f'invalid {name} preimage fingerprint')
  if not flag and value is not None: raise RuntimeError(f'unexpected {name} preimage fingerprint')
 if not isinstance(d.get('files'),dict) or any(not safe_manifest_rel(rel) or not isinstance(h,str) or not re.fullmatch(r'[0-9a-f]{64}',h) for rel,h in d.get('files',{}).items()): raise RuntimeError('invalid installed manifest files')
 backup=home/META_NAME/'backups'/d['backupId']
 if not backup.is_dir() or backup.is_symlink(): raise RuntimeError('bound installed backup directory missing/unsafe')
 for name,flag,path,is_dir in (('patch',d['hadPatchPreimage'],backup/'cordis.patch.yml',False),('plugin',d['hadPluginPreimage'],backup/'plugin-preimage',True),('state',d['hadStatePreimage'],backup/'state-preimage',True)):
  if flag:
   if path.is_symlink() or (is_dir and not path.is_dir()) or (not is_dir and not path.is_file()): raise RuntimeError(f'installed backup preimage missing/unsafe: {name}')
   got=tree_fingerprint(path) if is_dir else file_sha(path)
   if got!=pre[name]: raise RuntimeError(f'installed backup preimage fingerprint mismatch: {name}')
 if not plugin.is_dir() or plugin.is_symlink(): raise RuntimeError('installed DSH plugin missing/unsafe')
 if patch.is_symlink() or not patch.is_file(): raise RuntimeError('DSH home patch registration missing/unsafe')
 text=patch.read_text(encoding='utf-8')
 if text.count(MARK_BEGIN)!=1 or text.count(MARK_END)!=1 or marker_block().rstrip('\n') not in text: raise RuntimeError('DSH home patch registration malformed')
 try:
  import yaml
  parsed=yaml.safe_load(text)
  if not isinstance(parsed,list): raise RuntimeError('DSH home patch is not a YAML sequence')
  matches=[x for x in parsed if isinstance(x,dict) and x.get('insert')==[{'id':'graphlean-gate','name':'./graphlean/plugin/index.js'}]]
  if len(matches)!=1: raise RuntimeError('DSH home patch lacks the exact GraphLean - insert entry')
 except ImportError: pass
 for rel,want in d['files'].items():
  p=plugin/rel
  if p.is_symlink() or not p.is_file(): raise RuntimeError(f'installed file missing/unsafe: {rel}')
  if hashlib.sha256(p.read_bytes()).hexdigest()!=want: raise RuntimeError(f'installed file drift: {rel}')
 if any(p.is_symlink() for p in plugin.rglob('*')): raise RuntimeError('installed plugin contains symlinks')
 actual={str(p.relative_to(plugin)).replace('\\','/') for p in plugin.rglob('*') if p.is_file()}
 if actual!=set(d['files']): raise RuntimeError('installed plugin contains unexpected files')
 pkg=json.loads((plugin/'package.json').read_text(encoding='utf-8'))
 expected_keys={'name','version','description','license','type','engines','main','exports'}
 if set(pkg)!=expected_keys or pkg.get('name')!='graphlean' or pkg.get('version')!=VERSION or pkg.get('type')!='module' or pkg.get('main')!='./index.js' or pkg.get('exports')!='./index.js' or pkg.get('license')!='MIT' or pkg.get('engines')!={'node':'^22.19.0 || >=24.0.0'}: raise RuntimeError('installed GraphLean plugin package metadata mismatch')
 for p in sorted((plugin/'graph'/'templates').glob('*.json'))+[plugin/'graph'/'quality'/'quality-improvement.json',plugin/'graph'/'evolution'/'self-evolution.json']:
  graphleanctl.validate_template(json.loads(p.read_text(encoding='utf-8')))
 print('PASS installed DSH relative plugin/patch/hash/session-graph validation')

def probe_dsh(home: Path,profile: str):
 exe=shutil.which('dsh')
 if not exe: raise RuntimeError('dsh executable not found on PATH; cannot perform requested real-loader probe')
 env={**os.environ,'DSH_HOME':str(home.resolve())}
 r=subprocess.run([exe,'--profile',profile,'--dump-config'],env=env,text=True,capture_output=True,timeout=60)
 combined=(r.stdout or '')+'\n'+(r.stderr or '')
 if r.returncode!=0: raise RuntimeError(f'dsh --dump-config failed ({r.returncode}): {combined[-4000:]}')
 if 'graphlean-gate' not in combined or './graphlean/plugin/index.js' not in combined: raise RuntimeError('DSH dump-config succeeded but GraphLean entry was not present')
 print(f'PASS real DSH loader probe profile={profile}')


def bundle_test():
 pkg_path=ROOT/'package.json'; patch_path=ROOT/'cordis.patch.yml'
 if not pkg_path.is_file() or not patch_path.is_file(): raise RuntimeError('official DSH bundle files missing')
 pkg=json.loads(pkg_path.read_text(encoding='utf-8'))
 if pkg.get('name')!='graphlean' or pkg.get('version')!=VERSION or pkg.get('type')!='module' or pkg.get('main')!='./dsh/index.js' or pkg.get('exports')!='./dsh/index.js' or pkg.get('license')!='MIT': raise RuntimeError('official DSH bundle package metadata mismatch')
 if pkg.get('engines')!={'node':'^22.19.0 || >=24.0.0'} or pkg.get('dsh')!={'bundle':{'patch':'./cordis.patch.yml'}} or pkg.get('bin')!={'graphleanctl':'./bin/graphleanctl.mjs'}: raise RuntimeError('official DSH bundle contract mismatch')
 if patch_path.read_text(encoding='utf-8') != "- insert:\n    - id: graphlean-gate\n      name: graphlean\n": raise RuntimeError('official DSH bundle patch mismatch')
 print('PASS official DSH bundle manifest/patch validation')

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--target',help='DSH_HOME to validate after installation'); ap.add_argument('--probe-dsh',action='store_true'); ap.add_argument('--profile',default='web'); ap.add_argument('--source-tree',action='store_true',help='validate a Git/source checkout instead of a staged release payload'); args=ap.parse_args()
 has_manifest=(ROOT/'MANIFEST.json').is_file(); has_checksums=(ROOT/'CHECKSUMS.sha256').is_file()
 if has_manifest != has_checksums: raise RuntimeError('partial release integrity metadata')
 source_tree=args.source_tree or not has_manifest
 rc=graphleanctl.cmd_selftest(ROOT, source_tree=source_tree)
 if rc:return rc
 bundle_test()
 if args.probe_dsh and not args.target: raise RuntimeError('--probe-dsh requires --target DSH_HOME')
 if args.target:
  home=Path(args.target).expanduser(); installed_test(home)
  if args.probe_dsh: probe_dsh(home,args.profile)
 return 0
if __name__=='__main__':
 try: raise SystemExit(main())
 except Exception as e: print(f'FAIL {e}',file=sys.stderr); raise SystemExit(1)
