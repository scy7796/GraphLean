#!/usr/bin/env python3
from __future__ import annotations
import sys; sys.dont_write_bytecode=True
import argparse, hashlib, json, os, shutil, subprocess, tarfile, tempfile, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
VERSION='1.0.0'
BASENAME=f'graphlean-{VERSION}'
EXCLUDED_NAMES={'MANIFEST.json','CHECKSUMS.sha256'}
EXCLUDED_PARTS={'__pycache__','.pytest_cache','.git','dist','build'}


def sha(p: Path): return hashlib.sha256(p.read_bytes()).hexdigest()

def payload_files(root: Path):
    out=[]
    for p in root.rglob('*'):
        if not p.is_file() or p.is_symlink(): continue
        rel=p.relative_to(root)
        if p.name in EXCLUDED_NAMES or any(x in EXCLUDED_PARTS for x in rel.parts): continue
        if p.suffix in {'.pyc','.pyo'}: continue
        out.append(p)
    return sorted(out,key=lambda p:p.relative_to(root).as_posix())

def write_integrity(root: Path):
    files={p.relative_to(root).as_posix():sha(p) for p in payload_files(root)}
    manifest={'schemaVersion':1,'version':VERSION,'files':files}
    mraw=json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n'
    (root/'MANIFEST.json').write_text(mraw,encoding='utf-8')
    mh=sha(root/'MANIFEST.json')
    lines=[f'{h}  {rel}' for rel,h in files.items()]+[f'{mh}  MANIFEST.json']
    (root/'CHECKSUMS.sha256').write_text('\n'.join(lines)+'\n',encoding='utf-8')

def env_no_bytecode(): return {**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}

def run(cmd,cwd):
    print('+',' '.join(map(str,cmd)))
    subprocess.run(list(map(str,cmd)),cwd=cwd,env=env_no_bytecode(),check=True)

def capture(cmd,cwd):
    print('+',' '.join(map(str,cmd)))
    return subprocess.run(list(map(str,cmd)),cwd=cwd,env=env_no_bytecode(),check=True,text=True,capture_output=True)

def snapshot(root: Path):
    rows=[]
    if not root.exists(): return rows
    for p in sorted(root.rglob('*'),key=lambda x:x.relative_to(root).as_posix()):
        rel=p.relative_to(root).as_posix()
        if p.is_symlink(): rows.append(('L',rel,os.readlink(p)))
        elif p.is_dir(): rows.append(('D',rel,''))
        elif p.is_file(): rows.append(('F',rel,sha(p),oct(p.stat().st_mode & 0o777)))
    return rows

def deterministic_zip(src: Path,out: Path):
    epoch=(2026,1,1,0,0,0)
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(src.rglob('*'),key=lambda x:x.relative_to(src.parent).as_posix()):
            if p.is_dir(): continue
            arc=p.relative_to(src.parent).as_posix()
            info=zipfile.ZipInfo(arc,epoch); info.compress_type=zipfile.ZIP_DEFLATED
            mode=0o755 if os.access(p,os.X_OK) else 0o644
            info.external_attr=(mode & 0xFFFF)<<16; info.create_system=3
            z.writestr(info,p.read_bytes())

def verify_tgz(path: Path):
    required={'package/package.json','package/cordis.patch.yml','package/dsh/index.js','package/README.md','package/LICENSE','package/bin/graphleanctl.mjs','package/graphleanctl.py','package/benchmarks/measure-context-surface.mjs','package/benchmarks/context-surface.json','package/docs/RELEASE_VALIDATION.md','package/SECURITY.md'}
    graph_count=0
    with tarfile.open(path,'r:gz') as tf:
        members=tf.getmembers(); names=set()
        for m in members:
            name=m.name.replace('\\','/')
            parts=Path(name).parts
            if name.startswith('/') or '..' in parts: raise RuntimeError(f'unsafe npm tar path: {name}')
            if m.issym() or m.islnk(): raise RuntimeError(f'symlink/hardlink forbidden in npm tar: {name}')
            names.add(name)
            if name.startswith('package/graph/') and name.endswith('.json') and '/patterns/' not in name: graph_count += 1
        missing=required-names
        if missing: raise RuntimeError('npm tarball missing required files: '+', '.join(sorted(missing)))
        if graph_count != 10: raise RuntimeError(f'npm tarball executable graph count mismatch: {graph_count}')
        pkg=json.load(tf.extractfile('package/package.json'))
        if pkg.get('name')!='graphlean' or pkg.get('version')!=VERSION or pkg.get('dsh')!={'bundle':{'patch':'./cordis.patch.yml'}} or pkg.get('bin')!={'graphleanctl':'./bin/graphleanctl.mjs'}: raise RuntimeError('npm tarball DSH bundle metadata mismatch')
    print(f'PASS npm tarball inspection entries={len(names)} executable_graphs={graph_count}')

def npm_pack(stage: Path, packdir: Path):
    npm=shutil.which('npm')
    if not npm: raise RuntimeError('npm is required for release bundle validation')
    dry=capture([npm,'pack','--dry-run','--json'],stage)
    data=json.loads(dry.stdout)
    if not isinstance(data,list) or len(data)!=1 or data[0].get('name')!='graphlean' or data[0].get('version')!=VERSION:
        raise RuntimeError('npm pack --dry-run metadata mismatch')
    packdir.mkdir(parents=True,exist_ok=True)
    actual=capture([npm,'pack','--json','--pack-destination',packdir],stage)
    rows=json.loads(actual.stdout)
    if not isinstance(rows,list) or len(rows)!=1: raise RuntimeError('npm pack did not return exactly one artifact')
    tgz=packdir/rows[0]['filename']
    if not tgz.is_file(): raise RuntimeError('npm pack artifact missing')
    verify_tgz(tgz)
    return tgz

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output-dir',default=str(ROOT.parent)); args=ap.parse_args()
    outdir=Path(args.output_dir).expanduser().resolve(); outdir.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        work=Path(td); stage=work/BASENAME; stage.mkdir()
        for p in payload_files(ROOT):
            rel=p.relative_to(ROOT); dst=stage/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dst)
        write_integrity(stage)

        run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],stage)
        run([sys.executable,'-B','SELFTEST.py'],stage)
        run(['node','--check','dsh/index.js'],stage)
        run(['node','--check','bin/graphleanctl.mjs'],stage)
        run(['node','bin/graphleanctl.mjs','--help'],stage)

        with tempfile.TemporaryDirectory() as hd:
            home=Path(hd)/'dsh-home'; home.mkdir()
            (home/'cordis.patch.yml').write_text("- insert:\n    - id: preexisting\n      name: './preexisting.js'\n",encoding='utf-8')
            pre=snapshot(home)
            run([sys.executable,'-B','INSTALL.py','--dsh-home',home,'--probe-dsh','never'],stage)
            run([sys.executable,'-B','SELFTEST.py','--target',home],stage)
            run([sys.executable,'-B','UNINSTALL.py','--dsh-home',home],stage)
            if snapshot(home)!=pre: raise RuntimeError('install/uninstall preimage mismatch in release smoke')

        # Build the official DSH bundle twice; identical bytes are required.
        tgz1=npm_pack(stage,work/'pack1')
        tgz2=npm_pack(stage,work/'pack2')
        if sha(tgz1)!=sha(tgz2): raise RuntimeError('npm bundle is not reproducible across two identical packs')

        zip1=work/'one.zip'; zip2=work/'two.zip'
        deterministic_zip(stage,zip1); deterministic_zip(stage,zip2)
        if sha(zip1)!=sha(zip2): raise RuntimeError('source ZIP is not reproducible across two identical builds')

        zip_path=outdir/f'{BASENAME}.zip'; tgz_path=outdir/tgz1.name
        shutil.copy2(zip1,zip_path); shutil.copy2(tgz1,tgz_path)
        zh=sha(zip_path); th=sha(tgz_path)
        (outdir/f'{zip_path.name}.sha256').write_text(f'{zh}  {zip_path.name}\n',encoding='utf-8')
        (outdir/f'{tgz_path.name}.sha256').write_text(f'{th}  {tgz_path.name}\n',encoding='utf-8')
        (outdir/'SHA256SUMS.txt').write_text(f'{zh}  {zip_path.name}\n{th}  {tgz_path.name}\n',encoding='utf-8')

        shutil.copy2(stage/'MANIFEST.json',ROOT/'MANIFEST.json')
        shutil.copy2(stage/'CHECKSUMS.sha256',ROOT/'CHECKSUMS.sha256')
        print(f'RELEASE ZIP {zip_path}'); print(f'SHA256 {zh}')
        print(f'RELEASE DSH BUNDLE {tgz_path}'); print(f'SHA256 {th}')

if __name__=='__main__': main()

