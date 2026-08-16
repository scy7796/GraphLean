import json, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import graphleanctl
class EvolutionTests(unittest.TestCase):
 def test_evolution_is_graph_and_approval_is_session_bound(self):
  evo=json.loads((ROOT/'graph/evolution/self-evolution.json').read_text(encoding='utf-8')); graphleanctl.validate_template(evo)
  self.assertEqual('gt_self_evolution',evo['template_id']); self.assertEqual(2,evo['version'])
  self.assertTrue(any(n['id']=='n_approval' and n['type']=='approval' for n in evo['nodes']))
  self.assertEqual('read_only',next(n for n in evo['nodes'] if n['id']=='n_candidate')['authority'])
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); session=root/'sessions'/('a'*64); session.mkdir(parents=True); run='run_'+'1'*24; template_id='gt_self_evolution'; template_hash='f'*64
   action={'tool_name':'write','arguments':{'file_path':'x','content':'y'}}; ah=graphleanctl.stable_hash({'tool':'write','arguments':action['arguments']}); staged=[{'tool':'write','actionHash':ah}]; h=graphleanctl.stable_hash({'templateId':template_id,'templateHash':template_hash,'actions':staged}); review=session/f'candidate-review-{run}.json'; review.write_text(json.dumps({'schemaVersion':1,'runId':run,'candidateHash':h,'actionHashes':[ah],'actions':[action]}),encoding='utf-8'); import hashlib; rh=hashlib.sha256(review.read_bytes()).hexdigest(); (session/'active.json').write_text(json.dumps({'runId':run,'templateId':template_id,'templateHash':template_hash,'currentNode':'n_approval','candidateHash':h,'candidateReviewHash':rh,'approvedCandidateHash':None,'stagedActions':staged,'closed':False}),encoding='utf-8')
   p=graphleanctl.approve(root,run,h); token=json.loads(p.read_text()); self.assertEqual(h,token['candidateHash']); self.assertEqual(3,token['schemaVersion']); self.assertEqual(session.resolve(),p.parent.resolve())
   review.write_text(review.read_text().replace('"y"','"tampered"'))
   p.unlink()
   with self.assertRaises(graphleanctl.ValidationError): graphleanctl.approve(root,run,h)
   with self.assertRaises(graphleanctl.ValidationError): graphleanctl.approve(root,run,'b'*64)
 def test_approval_rejects_cross_session_duplicate_run(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); run='run_'+'2'*24; h='b'*64
   for key in ('a'*64,'b'*64):
    s=root/'sessions'/key; s.mkdir(parents=True); (s/'active.json').write_text(json.dumps({'runId':run,'currentNode':'n_approval','candidateHash':h,'approvedCandidateHash':None,'closed':False}))
   with self.assertRaises(graphleanctl.ValidationError): graphleanctl.approve(root,run,h)
 def test_approval_cli_rejects_symlinked_session_or_review(self):
  import os
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/'state'; sessions=root/'sessions'; sessions.mkdir(parents=True); outside=Path(td)/'outside'; outside.mkdir(); h='d'*64; run='run_'+'3'*24
   review_data={'schemaVersion':1,'runId':run,'candidateHash':h,'actionHashes':['e'*64],'actions':[{'tool_name':'write','arguments':{'file_path':'x','content':'y'}}]}
   review=outside/f'candidate-review-{run}.json'; review.write_text(json.dumps(review_data),encoding='utf-8')
   import hashlib; rh=hashlib.sha256(review.read_bytes()).hexdigest(); (outside/'active.json').write_text(json.dumps({'runId':run,'currentNode':'n_approval','candidateHash':h,'candidateReviewHash':rh,'approvedCandidateHash':None,'stagedActions':[{'tool':'write','actionHash':'e'*64}],'closed':False}))
   link=sessions/('f'*64)
   try: link.symlink_to(outside,target_is_directory=True)
   except (OSError,NotImplementedError): self.skipTest('symlinks unavailable')
   with self.assertRaises(graphleanctl.ValidationError): graphleanctl.approve(root,run,h)
   self.assertFalse((outside/f'approval-{run}.json').exists())
 def test_out_of_band_recover_abort_archives_pending_run_without_replay(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); session=root/'sessions'/('9'*64); session.mkdir(parents=True); run='run_'+'4'*24
   active=session/'active.json'; active.write_text(json.dumps({'runId':run,'pendingCalls':[{'callKey':'a'*64}],'rawArgumentsPersisted':False}),encoding='utf-8')
   review=session/f'candidate-review-{run}.json'; approval=session/f'approval-{run}.json'; review.write_text('local raw review'); approval.write_text('{}')
   archived=graphleanctl.recover_abort(root,run)
   self.assertFalse(active.exists()); self.assertEqual((session/f'aborted-{run}.json').resolve(),archived.resolve()); self.assertTrue(archived.is_file()); self.assertFalse(review.exists()); self.assertFalse(approval.exists())
   with self.assertRaises(graphleanctl.ValidationError): graphleanctl.recover_abort(root,run)
