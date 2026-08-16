import json, shutil, subprocess, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))

class BundleTests(unittest.TestCase):
 def test_official_dsh_bundle_manifest(self):
  pkg=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))
  self.assertEqual('graphlean',pkg['name']); self.assertEqual('1.0.1',pkg['version'])
  self.assertEqual({'bundle':{'patch':'./cordis.patch.yml'}},pkg['dsh']); self.assertEqual({'graphleanctl':'./bin/graphleanctl.mjs'},pkg['bin'])
  self.assertEqual('./dsh/index.js',pkg['exports']); self.assertNotIn('private',pkg)
 def test_official_bundle_patch_resolves_package(self):
  text=(ROOT/'cordis.patch.yml').read_text(encoding='utf-8')
  self.assertEqual("- insert:\n    - id: graphlean-gate\n      name: graphlean\n",text)

 def test_operator_cli_wrapper(self):
  node=shutil.which('node'); self.assertIsNotNone(node)
  r=subprocess.run([node,str(ROOT/'bin/graphleanctl.mjs'),'--help'],cwd=ROOT,text=True,capture_output=True)
  self.assertEqual(0,r.returncode,r.stderr); self.assertIn('graphleanctl',r.stdout)
 def test_bundle_entry_can_see_graphs(self):
  self.assertTrue((ROOT/'dsh/index.js').is_file())
  self.assertEqual(8,len(list((ROOT/'graph/templates').glob('*.json'))))
  self.assertTrue((ROOT/'graph/evolution/self-evolution.json').is_file())
