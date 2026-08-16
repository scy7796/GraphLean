import hashlib, json, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import graphleanctl

class PrivacyTests(unittest.TestCase):
 def test_release_is_clean(self): self.assertEqual([],graphleanctl.release_privacy_scan(ROOT))
 def test_secret_filenames_and_tokens_are_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); (root/'.env').write_text('SAFE_PLACEHOLDER=1')
   (root/'note.txt').write_text('xoxb-'+'A'*30)
   issues=graphleanctl.release_privacy_scan(root)
   self.assertTrue(any('.env' in x for x in issues)); self.assertTrue(any('privacy pattern' in x for x in issues))
 def test_symlink_is_rejected_when_supported(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); target=root/'target.txt'; target.write_text('x')
   link=root/'link.txt'
   try: link.symlink_to(target)
   except (OSError,NotImplementedError): self.skipTest('symlinks unavailable')
   self.assertTrue(any('forbidden symlink' in x for x in graphleanctl.release_privacy_scan(root)))
 def _make_release(self, root: Path):
  (root/'payload.txt').write_text('payload',encoding='utf-8')
  h=hashlib.sha256((root/'payload.txt').read_bytes()).hexdigest()
  manifest={'schemaVersion':1,'version':graphleanctl.RELEASE_VERSION,'files':{'payload.txt':h}}
  (root/'MANIFEST.json').write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
  mh=hashlib.sha256((root/'MANIFEST.json').read_bytes()).hexdigest()
  (root/'CHECKSUMS.sha256').write_text(f"{h}  payload.txt\n{mh}  MANIFEST.json\n",encoding='utf-8')

 def test_release_manifest_rejects_duplicate_checksum_entries(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); self._make_release(root)
   text=(root/'CHECKSUMS.sha256').read_text(); first=text.splitlines()[0]
   (root/'CHECKSUMS.sha256').write_text(text+first+'\n')
   with self.assertRaises(graphleanctl.ValidationError): graphleanctl.verify_release_manifest(root)

 def test_release_manifest_rejects_unsafe_or_extra_root_fields(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); self._make_release(root)
   d=json.loads((root/'MANIFEST.json').read_text()); d['files']={'../escape.txt':'0'*64}; d['surprise']=True
   (root/'MANIFEST.json').write_text(json.dumps(d))
   with self.assertRaises(graphleanctl.ValidationError): graphleanctl.verify_release_manifest(root)



