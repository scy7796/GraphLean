import json
import os, shutil, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class DshPluginTests(unittest.TestCase):
 def run_node(self, body):
  node=shutil.which('node')
  if not node:self.fail('Node.js is required for DSH plugin behavior tests; skipping would create a false-green release')
  with tempfile.TemporaryDirectory() as td:
   t=Path(td); pkg=t/'plugin'; pkg.mkdir(parents=True)
   shutil.copy2(ROOT/'dsh/index.js',pkg/'index.js'); meta=json.loads((ROOT/'package.json').read_text()); meta['main']='./index.js'; meta['exports']='./index.js'; meta.pop('files',None); meta.pop('dsh',None); meta.pop('keywords',None); meta.pop('bin',None); (pkg/'package.json').write_text(json.dumps(meta)); shutil.copytree(ROOT/'graph',pkg/'graph')
   script=t/'test.mjs'; script.write_text(body,encoding='utf-8')
   r=subprocess.run([node,str(script)],cwd=t,env={**os.environ,'STATE':str(t/'state'),'DSH_HOME':str(t/'dsh-home')},text=True,capture_output=True)
   self.assertEqual(0,r.returncode,r.stderr+'\n'+r.stdout); self.assertIn('PASS',r.stdout)

 def test_exact_classifier_session_isolation_and_branch_scheduler(self):
  self.run_node(r"""
import { apply } from './plugin/index.js'
const defs=new Map();let guard;const listeners=new Map();
const ctx={tools:{guard(fn){guard=fn;return()=>{}},register(def){defs.set(def.name,def);return()=>{}}},on(n,f){listeners.set(n,f);return()=>{}}};
let badConfig=false; try { apply(ctx,{stateRoot:process.env.STATE,readOnlyTools:['run_code']}) } catch { badConfig=true } if(!badConfig)throw new Error('hard-deny run_code was administrator-reclassifiable');
let badBuiltinConfig=false; try { apply(ctx,{stateRoot:process.env.STATE,readOnlyTools:['write']}) } catch { badBuiltinConfig=true } if(!badBuiltinConfig)throw new Error('built-in write was administrator-reclassifiable as read-only');
let badUnknownConfig=false; try { apply(ctx,{stateRoot:process.env.STATE,surprise:true}) } catch { badUnknownConfig=true } if(!badUnknownConfig)throw new Error('unknown plugin config key was silently accepted');
apply(ctx,{stateRoot:process.env.STATE});
if(defs.size!==5)throw new Error('control tool count mismatch');
for (const def of defs.values()) {
  if (!def.parameters || def.parameters.type !== 'object') throw new Error(`raw ToolDefinition schema missing for ${def.name}`)
  if (!def.output || typeof def.output.schema !== 'object') throw new Error(`raw output schema missing for ${def.name}`)
}
const pre=listeners.get('tools/pre-execute'); if(!pre)throw new Error('activation approval pre-execute gate missing');
const approvalExec={token:Symbol('approved-activation'),callId:'approval-call',name:'graphlean_begin',arguments:{template_id:'gt_inline_micro'},agent:{id:'approval-probe',session:{header:{id:'approval-session'}}}}; const activationDecision=await pre(approvalExec,async()=>({kind:'allow'})); if(activationDecision?.kind!=='ask')throw new Error('privileged graph selection was model-self-authorizing'); if(guard(approvalExec)!==undefined)throw new Error('approved privileged activation ticket was not accepted by monotonic guard'); const skippedApproval={token:Symbol('skipped-activation'),callId:'skipped-call',name:'graphlean_begin',arguments:{template_id:'gt_inline_micro'},agent:{id:'approval-probe-2',session:{header:{id:'skipped-session'}}}}; if(guard(skippedApproval)===undefined)throw new Error('privileged graph begin bypassed approval listener and still passed monotonic guard'); if(guard(approvalExec)===undefined)throw new Error('activation ticket was replayable');
let invalidBegin=false; try { await defs.get('graphlean_begin').execute({template_id:'gt_inline_micro', surprise:true},{agent:{id:'invalid',session:{header:{id:'invalid-session'}}}}) } catch { invalidBegin=true }
if(!invalidBegin)throw new Error('raw begin tool failed to enforce exact arguments');
const branchProbe={agent:{id:'branch-probe',session:{header:{id:'branch-session',cwd:process.cwd()}}}}; const bundled=await defs.get('graphlean_begin').execute({template_id:'gt_adaptive_execution',optional_nodes:['n_repair']},branchProbe); if(JSON.stringify(bundled.selectedOptionalNodes)!==JSON.stringify(['n_advisor','n_repair','n_reverify']))throw new Error('optional branch bundle was only partially selected'); await defs.get('graphlean_abort').execute({},branchProbe);
const hypoProbe={agent:{id:'hypo-probe',session:{header:{id:'hypo-session',cwd:process.cwd()}}}}; const hypo=await defs.get('graphlean_begin').execute({template_id:'gt_hypothesis_diagnosis'},hypoProbe); if(hypo.currentNode!=='n_frame')throw new Error(`minimal hypothesis profile exposed premature root ${hypo.currentNode}`); await defs.get('graphlean_abort').execute({},hypoProbe);
const cwd=process.cwd(); const A={agent:{id:'agent-A',session:{header:{id:'session-A',cwd}}}}, A2={agent:{id:'agent-A',session:{header:{id:'session-A2',cwd}}}}, B={agent:{id:'agent-B',session:{header:{id:'session-B',cwd}}}}; let seq=0;
const call=(name,args,exec=A)=>({callId:`call-${++seq}`,name,arguments:args??{},...exec});
if(guard(call('read_then_delete',{} ,A))===undefined)throw new Error('prefix read bypass survived');
if(guard(call('search_and_write',{},A))===undefined)throw new Error('prefix search bypass survived');
if(guard(call('bash',{command:'true'},A))===undefined)throw new Error('shell must be hard denied');
if(guard(call('workflow',{steps:[]},A))===undefined)throw new Error('composite workflow must be hard denied');
const NO_CWD={agent:{id:'no-cwd',session:{header:{id:'session-no-cwd'}}}}; if(guard(call('read',{file_path:'relative.txt'},NO_CWD))===undefined)throw new Error('relative filesystem path without trusted session cwd was allowed');
if(guard(call('read',{file_path:'x'},A))!==undefined)throw new Error('exact read denied');
if(guard(call('read',{file_path:'../outside-workspace-secret'},A))===undefined)throw new Error('workspace escape read was allowed');
if(guard(call('write',{file_path:'inside.txt',content:'x',sandbox_permissions:'danger-full-access',justification:'escape'},A))===undefined)throw new Error('filesystem sandbox escalation was allowed');
if(guard(call('read',{file_path:process.env.STATE+'/sessions/secret'},A))===undefined)throw new Error('control-plane read was exposed');
if(guard(call('read',{file_path:process.env.DSH_HOME+'/other-harness-private.json'},A))===undefined)throw new Error('non-GraphLean DSH_HOME private state was exposed');
const { writeFileSync: writeFs, symlinkSync } = await import('node:fs'); const { join: joinPath } = await import('node:path'); const outside=joinPath(cwd,'..','gw-outside-'+Date.now()+'.txt'); writeFs(outside,'secret'); const link=joinPath(cwd,'escape-link'); try { symlinkSync(outside,link); if(guard(call('read',{file_path:'escape-link'},A))===undefined)throw new Error('symlink workspace breakout was allowed') } catch(e) { if(e?.message==='symlink workspace breakout was allowed')throw e }
const G={agent:{id:'agent-G',session:{header:{id:'session-G',cwd:(await import('node:path')).dirname(process.env.DSH_HOME)}}}}; if(guard(call('read',{file_path:(await import('node:path')).basename(process.env.DSH_HOME)+'/graphlean/state/secret'},G))===undefined)throw new Error('relative session-cwd control-plane read bypass survived');
if(guard(call('glob',{pattern:'**/*',path:process.env.DSH_HOME},A))===undefined)throw new Error('discovery scope containing control plane was exposed');
if(guard(call('web_search',{query:'network without graph'},A))===undefined)throw new Error('network egress was treated as graphless read-only');
if(guard(call('ask_user_question',{questions:[{question:'clarify'}]},A))!==undefined)throw new Error('safe user clarification was unnecessarily graph-gated');
if(guard(call('str_replace_editor',{command:'view',path:'x'},A))!==undefined)throw new Error('editor view denied');
if(guard(call('str_replace_editor',{command:'create',path:'x',file_text:'x'},A))===undefined)throw new Error('editor mutation bypass');
if(guard(call('str_replace_editor',{command:'future_mutating_command',path:'x'},A))===undefined)throw new Error('unknown editor command was guessed into an authority class');
if(guard(call('run_code',{code:'return 1',description:'read only'},A))===undefined)throw new Error('run_code must be hard denied because DSH documents its runtime as bash-equivalent');
if(guard(call('skill',{name:'anything'},A))===undefined)throw new Error('native DSH skill surface must be hard denied in graph-only core');
if(guard(call('cordis_inspect_query',{query:'source'},A))===undefined)throw new Error('dynamic Cordis introspection must be hard denied in graph-only core');
const H={agent:{id:'agent-H',session:{header:{id:'session-H',cwd}}}}; await defs.get('graphlean_begin').execute({template_id:'gt_inline_micro'},H);
const bind=call('ask_user_question',{questions:[{question:'a'}]},H); if(guard(bind)!==undefined)throw new Error('binding probe admission denied');
listeners.get('tools/result')({...bind,arguments:{questions:[{question:'MUTATED'}]}},{isError:false,value:{ok:true}});
const { createHash: bindHash } = await import('node:crypto'); const { readFileSync: bindRead } = await import('node:fs'); const { join: bindJoin } = await import('node:path');
const hk=bindHash('sha256').update('agent-H\0session-H').digest('hex'); const bindRows=bindRead(bindJoin(process.env.STATE,'sessions',hk,'receipts.jsonl'),'utf8').trim().split(/\r?\n/).map(JSON.parse); if(!bindRows.at(-1).isError)throw new Error('tool/result execution-binding mismatch was accepted as success');
let bindAdvance=false; try { await defs.get('graphlean_advance').execute({},H) } catch { bindAdvance=true } if(!bindAdvance)throw new Error('binding-mismatched result satisfied an external-action node');
await defs.get('graphlean_abort').execute({},H);
const C={agent:{id:'agent-C',session:{header:{id:'session-C',cwd}}}}; await defs.get('graphlean_begin').execute({template_id:'gt_inline_micro'},C);
if(guard(call('mcp_unknown_side_effect',{},C))===undefined)throw new Error('unclassified tool allowed at external node');
if(guard(call('bash',{command:'true'},C))===undefined)throw new Error('unbounded shell allowed without explicit classification');
const bounded1=call('ask_user_question',{questions:[]},C); if(guard(bounded1)!==undefined)throw new Error('user interaction denied inside graph');
const bounded2=call('ask_user_question',{questions:[]},C); if(guard(bounded2)===undefined)throw new Error('parallel budget oversubscription allowed');
listeners.get('tools/result')(bounded1,{isError:false,value:undefined}); if(guard(bounded2)!==undefined)throw new Error('parallel slot did not release after result'); listeners.get('tools/result')(bounded2,{isError:false,value:{ok:true}});
let fakeExternalComplete=false; try { await defs.get('graphlean_advance').execute({},C) } catch { fakeExternalComplete=true } if(!fakeExternalComplete)throw new Error('user interaction falsely satisfied an external-action node');
const web=call('web_search',{query:'public evidence'},C); if(guard(web)!==undefined)throw new Error('explicit network/external action denied at external node'); listeners.get('tools/result')(web,{isError:false,value:{ok:true}});
const reportProbe=call('report',{content:'bounded parent report'},C); if(guard(reportProbe)!==undefined)throw new Error('DSH subagent report was not classified as external_action'); listeners.get('tools/result')(reportProbe,{isError:false,value:{ok:true}});
if(guard(call('write',{file_path:'external-node-must-not-write',content:'x'},C))===undefined)throw new Error('external_action authority incorrectly inherited workspace_write');
const aborted=await defs.get('graphlean_abort').execute({},C); if(!aborted.aborted)throw new Error('abort did not terminate active session');
if(guard(call('write',{file_path:'after-abort',content:'x'},C))===undefined)throw new Error('mutation remained authorized after abort');
let s=await defs.get('graphlean_begin').execute({template_id:'gt_multi_artifact'},A);
if(s.currentNode!=='n_plan')throw new Error('wrong root');
if(guard(call('write',{file_path:'x',content:'x'},B))===undefined)throw new Error('agent B inherited agent A graph');
if(guard(call('write',{file_path:'x',content:'x'},A2))===undefined)throw new Error('same agent id in a different DSH session inherited the active graph');
s=await defs.get('graphlean_advance').execute({},A);
if(s.currentNode!=='n_artifact_a')throw new Error('branch A not scheduled first');
const controlPlane=call('write',{file_path:process.env.STATE+'/owned.json',content:'tamper'},A); if(guard(controlPlane)===undefined)throw new Error('GraphLean state root was writable from a workspace-write node');
const patchPlane=call('write',{file_path:process.env.DSH_HOME+'/cordis.patch.yml',content:'tamper'},A); if(guard(patchPlane)===undefined)throw new Error('DSH home patch was writable from a workspace-write node');
let e=call('write',{file_path:'a',content:'A-SECRET'},A); if(guard(e)!==undefined)throw new Error('A write denied');
listeners.get('tools/result')(e,{isError:false,value:{ok:true}});
s=await defs.get('graphlean_advance').execute({},A);
if(s.closed || s.currentNode!=='n_artifact_b')throw new Error('DAG closed before branch B');
e=call('write',{file_path:'b',content:'B-SECRET'},A); if(guard(e)!==undefined)throw new Error('B write denied');
listeners.get('tools/result')(e,{isError:false,value:{ok:true}});
s=await defs.get('graphlean_advance').execute({},A);
if(s.currentNode!=='n_join')throw new Error('join not scheduled after both branches');
const D={agent:{id:'agent-D',session:{header:{id:'session-D',cwd}}}}; await defs.get('graphlean_begin').execute({template_id:'gt_inline_micro'},D);
const { createHash } = await import('node:crypto'); const { readFileSync, writeFileSync } = await import('node:fs'); const { join } = await import('node:path');
const dk=createHash('sha256').update('agent-D\0session-D').digest('hex'); const dp=join(process.env.STATE,'sessions',dk,'active.json'); const corrupt=JSON.parse(readFileSync(dp,'utf8')); corrupt.currentNode='n_verify_close'; writeFileSync(dp,JSON.stringify(corrupt));
if(guard(call('write',{file_path:'tamper-target',content:'x'},D))===undefined)throw new Error('structurally corrupted state did not fail closed');
const F={agent:{id:'agent-F',session:{header:{id:'session-F',cwd}}}}; await defs.get('graphlean_begin').execute({template_id:'gt_inline_micro'},F); const fk=createHash('sha256').update('agent-F\0session-F').digest('hex'); const fp=join(process.env.STATE,'sessions',fk,'active.json'); const expired=JSON.parse(readFileSync(fp,'utf8')); expired.startedAt='2000-01-01T00:00:00.000Z'; writeFileSync(fp,JSON.stringify(expired));
if(guard(call('ask_user_question',{questions:[]},F))===undefined)throw new Error('max_total_latency_ms was decorative');
console.log('PASS')
""")

 def test_self_evolution_exact_approval_binding_and_no_raw_persistence(self):
  self.run_node(r"""
import { apply } from './plugin/index.js'
import { readdirSync, readFileSync, writeFileSync } from 'node:fs'; import { join } from 'node:path';
const defs=new Map();let guard;const listeners=new Map();
const ctx={tools:{guard(fn){guard=fn;return()=>{}},register(def){defs.set(def.name,def);return()=>{}}},on(n,f){listeners.set(n,f);return()=>{}}};
apply(ctx,{stateRoot:process.env.STATE}); const E={agent:{id:'evolution-agent',session:{header:{id:'evolution-session',cwd:process.cwd()}}}}; let seq=0; const call=(name,args)=>({callId:`evo-${++seq}`,name,arguments:args,...E});
let s=await defs.get('graphlean_begin').execute({template_id:'gt_self_evolution'},E);
for(const want of ['n_diagnose','n_propose','n_baseline','n_candidate']){s=await defs.get('graphlean_advance').execute({},E);if(s.currentNode!==want)throw new Error(`expected ${want}, got ${s.currentNode}`)}
const secret='SHOULD-NOT-BE-PERSISTED-RAW';
const staged=await defs.get('graphlean_stage_candidate').execute({actions:[
 {tool_name:'write',arguments:{file_path:'approved-1.txt',content:secret}},
 {tool_name:'write',arguments:{file_path:'approved-2.txt',content:'SECOND'}}
]},E);
const session=join(process.env.STATE,'sessions',readdirSync(join(process.env.STATE,'sessions'))[0]);
if(readFileSync(join(session,'active.json'),'utf8').includes(secret))throw new Error('raw candidate args leaked into active state');
const review=join(session,`candidate-review-${s.runId}.json`); if(!readFileSync(review,'utf8').includes(secret))throw new Error('local human review packet missing exact candidate');
if(guard(call('read',{file_path:review}))===undefined)throw new Error('model could read raw local candidate review packet');
s=await defs.get('graphlean_advance').execute({},E); if(s.currentNode!=='n_replay')throw new Error('candidate did not advance');
for(const want of ['n_attack','n_decide','n_approval']){s=await defs.get('graphlean_advance').execute({},E);if(s.currentNode!==want)throw new Error(`expected ${want}`)}
const reviewBytes=readFileSync(review,'utf8');
writeFileSync(join(session,`approval-${s.runId}.json`),JSON.stringify({schemaVersion:3,runId:s.runId,candidateHash:staged.candidateHash}));
writeFileSync(review,reviewBytes+'\nTAMPERED-AFTER-APPROVAL'); let reviewTamperRejected=false; try { await defs.get('graphlean_advance').execute({},E) } catch { reviewTamperRejected=true } if(!reviewTamperRejected)throw new Error('review packet mutation after approval was accepted');
writeFileSync(review,reviewBytes);
s=await defs.get('graphlean_advance').execute({},E); if(s.currentNode!=='n_apply')throw new Error('approval did not enter apply after exact reviewed bytes were restored');
import { existsSync } from 'node:fs'; if(existsSync(review))throw new Error('raw candidate review packet survived approval transition');
if(guard(call('write',{file_path:'other.txt',content:secret}))===undefined)throw new Error('unapproved apply mutation allowed');
const first=call('write',{file_path:'approved-1.txt',content:secret}); const second=call('write',{file_path:'approved-2.txt',content:'SECOND'});
if(guard(second)===undefined)throw new Error('approved actions may execute out of sealed order');
if(guard(first)!==undefined)throw new Error('first exact approved action denied'); listeners.get('tools/result')(first,{isError:false,value:{ok:true}});
if(guard(first)===undefined)throw new Error('duplicate approved action not denied');
if(guard(second)!==undefined)throw new Error('second exact approved action denied'); listeners.get('tools/result')(second,{isError:false,value:{ok:true}});
if(readFileSync(join(session,'receipts.jsonl'),'utf8').includes(secret))throw new Error('raw receipt args persisted');
s=await defs.get('graphlean_advance').execute({},E); if(s.currentNode!=='n_postverify')throw new Error('apply completion failed');
console.log('PASS')
""")

