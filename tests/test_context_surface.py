import json, shutil, subprocess, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class ContextSurfaceTests(unittest.TestCase):
    def test_context_surface_is_bounded_and_reproducible(self):
        node=shutil.which('node')
        self.assertIsNotNone(node,'Node is required to validate the DSH plugin context surface')
        r=subprocess.run([node,str(ROOT/'benchmarks/measure-context-surface.mjs')],cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(0,r.returncode,r.stderr)
        got=json.loads(r.stdout)
        stored=json.loads((ROOT/'benchmarks/context-surface.json').read_text(encoding='utf-8'))
        self.assertEqual(stored,got)
        self.assertEqual('GraphLean',got['product'])
        self.assertEqual('1.0.1',got['version'])
        self.assertEqual(2,got['schemaVersion'])
        self.assertEqual(5,got['modelVisibleControlTools'])
        self.assertEqual(0,got['systemPromptPolicyInjectionBytes'])
        self.assertEqual(0,got['registeredSystemPromptSections'])
        self.assertEqual(1587,got['modelVisibleJsonBytes'])
        self.assertEqual(10,got['hostGraphTemplates'])
        self.assertLessEqual(got['modelVisibleJsonBytes'],4096)
        self.assertGreater(got['hostGraphPayloadBytes'],got['modelVisibleJsonBytes']*10)
        self.assertEqual(1,got['registeredHostGuards'])
        self.assertEqual(['tools/pre-execute','tools/result'],got['registeredHostEvents'])
