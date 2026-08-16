import copy, itertools, json, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import graphleanctl
class TemplateTests(unittest.TestCase):
 def test_all_executable_templates_runtime_validate(self):
  files=graphleanctl.template_files(ROOT); self.assertEqual(10,len(files))
  for p in files: graphleanctl.validate_template(json.loads(p.read_text(encoding='utf-8')))
 def test_json_schema_validation(self):
  try: from jsonschema import Draft202012Validator
  except ImportError: self.skipTest('jsonschema dev dependency not installed')
  schema=json.loads((ROOT/'schemas/graph_template.schema.json').read_text(encoding='utf-8')); v=Draft202012Validator(schema)
  for p in graphleanctl.template_files(ROOT): self.assertEqual([],list(v.iter_errors(json.loads(p.read_text(encoding='utf-8')))),p.name)
 def test_patterns(self): graphleanctl.validate_patterns(ROOT)
 def test_legacy_dynamic_control_labels_are_rejected(self):
  d=json.loads((ROOT/'graph/templates/adaptive-execution.json').read_text(encoding='utf-8'))
  for legacy in ('retry','fallback','routes_to','handoff'):
   bad=copy.deepcopy(d); bad['control_edges'][0]['relation']=legacy
   with self.assertRaises(graphleanctl.ValidationError): graphleanctl.validate_template(bad)
 def test_real_cycle_is_rejected(self):
  d=json.loads((ROOT/'graph/templates/adaptive-execution.json').read_text(encoding='utf-8'))
  bad=copy.deepcopy(d); bad['control_edges'].append({'from':'n_close','to':'n_frame','relation':'precedes','reason':'synthetic cycle'})
  with self.assertRaises(graphleanctl.ValidationError): graphleanctl.validate_template(bad)
 def test_every_optional_branch_bundle_profile_has_one_root_one_sink_and_complete_schedule(self):
  relations=set(graphleanctl.CONTROL)
  for p in graphleanctl.template_files(ROOT):
   d=json.loads(p.read_text(encoding='utf-8'))
   for selected_tuple,active in graphleanctl.activation_profiles(d):
    completed=set(); indeg={n:0 for n in active}; outdeg={n:0 for n in active}
    for e in d['control_edges']:
     if e['relation'] in relations and e['from'] in active and e['to'] in active:
      indeg[e['to']]+=1; outdeg[e['from']]+=1
    self.assertEqual(1,sum(v==0 for v in indeg.values()),f"root ambiguity {p.name} optional={selected_tuple}")
    self.assertEqual(1,sum(v==0 for v in outdeg.values()),f"sink ambiguity {p.name} optional={selected_tuple}")
    while len(completed)<len(active):
     ready=[]
     for nid in sorted(active-completed):
      preds={e['from'] for e in d['control_edges'] if e['relation'] in relations and e['to']==nid and e['from'] in active}
      if preds <= completed: ready.append(nid)
     self.assertTrue(ready, f"deadlock in {p.name} optional={selected_tuple} remaining={sorted(active-completed)}")
     completed.add(ready[0])
    self.assertEqual(active,completed)
