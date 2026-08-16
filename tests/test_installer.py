import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ENV={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
class InstallerTests(unittest.TestCase):
 def runpy(self,*args): return subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,env=ENV,text=True,capture_output=True)
 def test_install_validate_uninstall_preserves_existing_patch_and_package(self):
  with tempfile.TemporaryDirectory() as td:
   home=Path(td); patch=home/'cordis.patch.yml'; original="- insert:\n    - id: existing-plugin\n      name: './existing.js'\n"; patch.write_text(original,encoding='utf-8')
   pre=home/'graphlean/plugin'; pre.mkdir(parents=True); (pre/'old.txt').write_text('preimage'); old_state=home/'graphlean/state'; old_state.mkdir(); (old_state/'old-state.txt').write_text('state-preimage')
   r=self.runpy(ROOT/'INSTALL.py','--dsh-home',home); self.assertEqual(0,r.returncode,r.stderr)
   text=patch.read_text(); self.assertIn('- insert:\n    - id: graphlean-gate',text)
   r=self.runpy(ROOT/'SELFTEST.py','--target',home); self.assertEqual(0,r.returncode,r.stderr)
   r=self.runpy(ROOT/'UNINSTALL.py','--dsh-home',home); self.assertEqual(0,r.returncode,r.stderr)
   self.assertEqual(original,patch.read_text(encoding='utf-8')); self.assertEqual('preimage',(pre/'old.txt').read_text()); self.assertEqual('state-preimage',(old_state/'old-state.txt').read_text()); self.assertFalse((home/'.graphlean-installer-v1.0.1').exists())
 def test_modified_install_aborts_without_partial_uninstall_then_explicit_restore(self):
  with tempfile.TemporaryDirectory() as td:
   home=Path(td); r=self.runpy(ROOT/'INSTALL.py','--dsh-home',home); self.assertEqual(0,r.returncode,r.stderr)
   p=home/'graphlean/plugin/index.js'; p.write_text(p.read_text()+'\n// local change\n')
   patch_before=(home/'cordis.patch.yml').read_text()
   r=self.runpy(ROOT/'UNINSTALL.py','--dsh-home',home); self.assertEqual(2,r.returncode); self.assertTrue(p.exists()); self.assertEqual(patch_before,(home/'cordis.patch.yml').read_text()); self.assertTrue((home/'.graphlean-installer-v1.0.1/install.json').exists())
   r=self.runpy(ROOT/'UNINSTALL.py','--dsh-home',home,'--restore-backup'); self.assertEqual(0,r.returncode,r.stderr); self.assertFalse((home/'graphlean/plugin').exists())
 def test_manifest_path_injection_is_rejected_before_destructive_action(self):
  with tempfile.TemporaryDirectory() as td:
   home=Path(td); r=self.runpy(ROOT/'INSTALL.py','--dsh-home',home); self.assertEqual(0,r.returncode,r.stderr)
   sentinel=home/'DO_NOT_DELETE'; sentinel.mkdir(); (sentinel/'x').write_text('safe')
   manifest=home/'.graphlean-installer-v1.0.1/install.json'; d=json.loads(manifest.read_text()); d['packagePath']=str(sentinel); manifest.write_text(json.dumps(d))
   r=self.runpy(ROOT/'UNINSTALL.py','--dsh-home',home,'--restore-backup'); self.assertEqual(2,r.returncode); self.assertTrue((sentinel/'x').exists()); self.assertTrue((home/'graphlean/plugin').exists())
 def test_malformed_existing_patch_fails_before_package_replacement(self):
  with tempfile.TemporaryDirectory() as td:
   home=Path(td); patch=home/'cordis.patch.yml'; patch.write_text('not-a-sequence: true\n')
   pre=home/'graphlean/plugin'; pre.mkdir(parents=True); (pre/'old.txt').write_text('unchanged')
   r=self.runpy(ROOT/'INSTALL.py','--dsh-home',home); self.assertEqual(2,r.returncode); self.assertEqual('unchanged',(pre/'old.txt').read_text()); self.assertEqual('not-a-sequence: true\n',patch.read_text()); self.assertFalse((home/'.graphlean-installer-v1.0.1').exists())


 def test_noncanonical_semantically_empty_patch_is_rejected_before_mutation(self):
  with tempfile.TemporaryDirectory() as td:
   home=Path(td); patch=home/'cordis.patch.yml'; original='# keep me\n---\n[]\n'; patch.write_text(original)
   pre=home/'graphlean/plugin'; pre.mkdir(parents=True); (pre/'old.txt').write_text('unchanged')
   r=self.runpy(ROOT/'INSTALL.py','--dsh-home',home); self.assertEqual(2,r.returncode); self.assertEqual(original,patch.read_text()); self.assertEqual('unchanged',(pre/'old.txt').read_text()); self.assertFalse((home/'.graphlean-installer-v1.0.1').exists())
 def test_preexisting_unmarked_graphlean_patch_entry_is_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   home=Path(td); patch=home/'cordis.patch.yml'; original="- insert:\n    - id: graphlean-gate\n      name: './other.js'\n"; patch.write_text(original)
   r=self.runpy(ROOT/'INSTALL.py','--dsh-home',home); self.assertEqual(2,r.returncode); self.assertEqual(original,patch.read_text()); self.assertFalse((home/'.graphlean-installer-v1.0.1').exists())


 def test_corrupted_bound_backup_is_rejected_before_uninstall(self):
  with tempfile.TemporaryDirectory() as td:
   home=Path(td); pre=home/'graphlean/plugin'; pre.mkdir(parents=True); (pre/'old.txt').write_text('original-preimage')
   r=self.runpy(ROOT/'INSTALL.py','--dsh-home',home); self.assertEqual(0,r.returncode,r.stderr)
   manifest=json.loads((home/'.graphlean-installer-v1.0.1/install.json').read_text()); backup=home/'.graphlean-installer-v1.0.1/backups'/manifest['backupId']/'plugin-preimage'/'old.txt'; backup.write_text('CORRUPTED')
   current=home/'graphlean/plugin/index.js'; before=current.read_bytes()
   r=self.runpy(ROOT/'SELFTEST.py','--target',home); self.assertEqual(1,r.returncode); self.assertIn('fingerprint mismatch',r.stderr+r.stdout)
   r=self.runpy(ROOT/'UNINSTALL.py','--dsh-home',home,'--restore-backup'); self.assertEqual(2,r.returncode); self.assertEqual(before,current.read_bytes()); self.assertTrue((home/'.graphlean-installer-v1.0.1/install.json').exists())

class InstallerFaultInjectionTests(unittest.TestCase):
 def load_installer(self):
  import importlib.util
  spec=importlib.util.spec_from_file_location('gw_install_fault',ROOT/'INSTALL.py'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
 def test_staging_commit_failure_restores_preimages(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as td:
   home=Path(td); patch_file=home/'cordis.patch.yml'; original="- insert:\n    - id: existing\n      name: './existing.js'\n"; patch_file.write_text(original)
   plugin=home/'graphlean/plugin'; plugin.mkdir(parents=True); (plugin/'old.txt').write_text('old-plugin')
   state=home/'graphlean/state'; state.mkdir(); (state/'old.txt').write_text('old-state')
   mod=self.load_installer(); real_replace=mod.os.replace
   def fail_commit(src,dst):
    if Path(src).name.startswith('.staging-') and Path(dst)==plugin: raise OSError('injected staging commit failure')
    return real_replace(src,dst)
   with patch.object(mod.os,'replace',side_effect=fail_commit):
    with self.assertRaises(OSError): mod.main(['--dsh-home',str(home)])
   self.assertEqual('old-plugin',(plugin/'old.txt').read_text()); self.assertEqual('old-state',(state/'old.txt').read_text()); self.assertEqual(original,patch_file.read_text()); self.assertFalse((home/'.graphlean-installer-v1.0.1').exists())
 def test_backup_failure_leaves_host_and_no_metadata(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as td:
   home=Path(td); plugin=home/'graphlean/plugin'; plugin.mkdir(parents=True); (plugin/'old.txt').write_text('old-plugin')
   mod=self.load_installer(); real_copytree=mod.copytree
   def fail_backup(src,dst):
    if Path(dst).name=='plugin-preimage': raise OSError('injected backup failure')
    return real_copytree(src,dst)
   with patch.object(mod,'copytree',side_effect=fail_backup):
    with self.assertRaises(OSError): mod.main(['--dsh-home',str(home)])
   self.assertEqual('old-plugin',(plugin/'old.txt').read_text()); self.assertFalse((home/'.graphlean-installer-v1.0.1').exists())

class InstallerSymlinkSafetyTests(unittest.TestCase):
 def runpy(self,*args): return subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,env=ENV,text=True,capture_output=True)
 def test_install_refuses_symlinked_patch(self):
  with tempfile.TemporaryDirectory() as td:
   home=Path(td); target=home/'real-patch.yml'; target.write_text('[]\n'); patch=home/'cordis.patch.yml'
   try: patch.symlink_to(target)
   except (OSError,NotImplementedError): self.skipTest('symlinks unavailable')
   r=self.runpy(ROOT/'INSTALL.py','--dsh-home',home); self.assertEqual(2,r.returncode); self.assertEqual('[]\n',target.read_text()); self.assertFalse((home/'.graphlean-installer-v1.0.1').exists())
 def test_uninstall_detects_nested_plugin_symlink_even_with_matching_content(self):
  with tempfile.TemporaryDirectory() as td:
   home=Path(td); r=self.runpy(ROOT/'INSTALL.py','--dsh-home',home); self.assertEqual(0,r.returncode,r.stderr)
   index=home/'graphlean/plugin/index.js'; twin=home/'matching-index.js'; twin.write_bytes(index.read_bytes()); index.unlink()
   try: index.symlink_to(twin)
   except (OSError,NotImplementedError): self.skipTest('symlinks unavailable')
   r=self.runpy(ROOT/'UNINSTALL.py','--dsh-home',home); self.assertEqual(2,r.returncode); self.assertTrue(index.is_symlink()); self.assertTrue((home/'.graphlean-installer-v1.0.1/install.json').exists())

class OneClickReleaseTests(unittest.TestCase):
 def runpy(self,*args,env=None): return subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,env=env or ENV,text=True,capture_output=True)
 def test_unix_one_click_round_trip(self):
  if os.name=='nt': self.skipTest('POSIX wrapper test')
  with tempfile.TemporaryDirectory() as td:
   home=Path(td)/'home'; home.mkdir(); pre=(home/'cordis.patch.yml'); pre.write_text("- insert:\n    - id: existing\n      name: './existing.js'\n",encoding='utf-8'); original=pre.read_bytes()
   r=subprocess.run(['sh',str(ROOT/'INSTALL_UNIX.sh'),'--dsh-home',str(home),'--probe-dsh','never'],cwd=ROOT,env=ENV,text=True,capture_output=True); self.assertEqual(0,r.returncode,r.stderr)
   self.assertTrue((home/'graphlean/plugin/index.js').is_file())
   r=subprocess.run(['sh',str(ROOT/'UNINSTALL_UNIX.sh'),'--dsh-home',str(home)],cwd=ROOT,env=ENV,text=True,capture_output=True); self.assertEqual(0,r.returncode,r.stderr)
   self.assertEqual(original,pre.read_bytes()); self.assertFalse((home/'.graphlean-installer-v1.0.1').exists())
 def test_auto_real_loader_probe_success_and_failure_rollback(self):
  if os.name=='nt': self.skipTest('POSIX fake executable test')
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); bindir=root/'bin'; bindir.mkdir(); dsh=bindir/'dsh'
   dsh.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$PROBE_ARGS\"\necho \"- id: graphlean-gate\"\necho \"  name: './graphlean/plugin/index.js'\"\n",encoding='utf-8'); dsh.chmod(0o755)
   home=root/'ok'; home.mkdir(); argslog=root/'args.txt'; env={**ENV,'PATH':str(bindir)+os.pathsep+os.environ.get('PATH',''),'PROBE_ARGS':str(argslog)}
   r=self.runpy(ROOT/'INSTALL.py','--dsh-home',home,'--probe-dsh','auto',env=env); self.assertEqual(0,r.returncode,r.stderr); self.assertIn('--dump-config',argslog.read_text()); self.assertTrue((home/'graphlean/plugin/index.js').is_file())
   self.assertEqual(0,self.runpy(ROOT/'UNINSTALL.py','--dsh-home',home,env=env).returncode)
   dsh.write_text("#!/bin/sh\necho loader-failed >&2\nexit 9\n",encoding='utf-8'); dsh.chmod(0o755)
   bad=root/'bad'; bad.mkdir(); patch=bad/'cordis.patch.yml'; original=b"- insert:\n    - id: existing\n      name: './existing.js'\n"; patch.write_bytes(original)
   r=self.runpy(ROOT/'INSTALL.py','--dsh-home',bad,'--probe-dsh','auto',env=env); self.assertNotEqual(0,r.returncode); self.assertEqual(original,patch.read_bytes()); self.assertFalse((bad/'graphlean/plugin').exists()); self.assertFalse((bad/'.graphlean-installer-v1.0.1').exists())
 def test_legacy_pre_graphlean_collision_is_refused_before_mutation(self):
  with tempfile.TemporaryDirectory() as td:
   home=Path(td); legacy=home/'graphweave'; legacy.mkdir(); (legacy/'sentinel').write_text('old')
   r=self.runpy(ROOT/'INSTALL.py','--dsh-home',home,'--probe-dsh','never'); self.assertNotEqual(0,r.returncode); self.assertTrue((legacy/'sentinel').is_file()); self.assertFalse((home/'graphlean').exists())
 def test_powershell_one_click_wrapper_is_present_and_fail_fast(self):
  text=(ROOT/'INSTALL_ONE_CLICK.ps1').read_text(encoding='utf-8'); self.assertIn("$ErrorActionPreference = 'Stop'",text); self.assertIn('--probe-dsh auto',text); self.assertIn('INSTALL.py',text)
