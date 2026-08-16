#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, re, sys, tempfile
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GRAPH_FIELDS = {"schema_version","template_id","version","description","activation","budgets","nodes","control_edges","reliance_edges","stop_conditions"}
BUDGET_FIELDS = {"max_nodes","max_model_nodes","max_edges","max_parallel_calls","max_tool_calls","max_total_latency_ms"}
NODE_TYPES = {"evidence","capability","operation","verifier","reducer","approval","checkpoint"}
AUTHORITIES = {"read_only","workspace_write","external_action"}
CONTROL = {"precedes","verifies"}
DAG_CONTROL = CONTROL
RELIANCE = {"reads","writes","uses","depends_on","derived_from","invalidates"}
GRADES = {"declared","inferred","observed"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
RUN_ID = re.compile(r"^run_[0-9a-f]{24}$")
RELEASE_VERSION = "1.0.0"

class ValidationError(ValueError): pass

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def stable_hash(obj) -> str:
    raw=json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def template_files(root: Path=ROOT):
    return sorted(list((root/"graph"/"templates").glob("*.json")) + [root/"graph"/"quality"/"quality-improvement.json", root/"graph"/"evolution"/"self-evolution.json"])

def _optional_components(d: dict):
    optional={n["id"] for n in d.get("nodes",[]) if isinstance(n,dict) and n.get("optional") is True}
    adj={x:set() for x in optional}
    for e in d.get("control_edges",[]):
        if isinstance(e,dict) and e.get("from") in optional and e.get("to") in optional:
            adj[e["from"]].add(e["to"]); adj[e["to"]].add(e["from"])
    comps=[]; seen=set()
    for start in sorted(optional):
        if start in seen: continue
        stack=[start]; comp=set()
        while stack:
            cur=stack.pop()
            if cur in seen: continue
            seen.add(cur); comp.add(cur); stack.extend(sorted(adj[cur]-seen, reverse=True))
        comps.append(tuple(sorted(comp)))
    return comps

def activation_profiles(d: dict):
    comps=_optional_components(d)
    if len(comps)>10: raise ValidationError("too many independent optional branch bundles (>10)")
    mandatory={n["id"] for n in d["nodes"] if not n["optional"]}
    for mask in range(1<<len(comps)):
        active=set(mandatory)
        selected=[]
        for i,comp in enumerate(comps):
            if mask & (1<<i): active.update(comp); selected.extend(comp)
        yield tuple(sorted(selected)), active

def _validate_activation_profiles(d: dict):
    for selected,active in activation_profiles(d):
        indeg={x:0 for x in active}; outdeg={x:0 for x in active}
        for e in d["control_edges"]:
            if e["from"] in active and e["to"] in active:
                indeg[e["to"]]+=1; outdeg[e["from"]]+=1
        roots=sorted(x for x,v in indeg.items() if v==0); sinks=sorted(x for x,v in outdeg.items() if v==0)
        if len(roots)!=1 or len(sinks)!=1:
            raise ValidationError(f"activation profile optional={list(selected)} must have exactly one root and one sink; roots={roots} sinks={sinks}")

def validate_template(d: dict) -> dict:
    if not isinstance(d,dict) or set(d)!=GRAPH_FIELDS or d.get("schema_version")!=1: raise ValidationError("malformed graph template root")
    if not isinstance(d.get("template_id"),str) or not re.fullmatch(r"gt_[A-Za-z0-9_-]{1,156}",d["template_id"]): raise ValidationError("invalid template_id")
    if isinstance(d.get("version"),bool) or not isinstance(d.get("version"),int) or d["version"]<1: raise ValidationError("invalid version")
    if not isinstance(d.get("description"),str) or not d["description"].strip(): raise ValidationError("missing description")
    a=d.get("activation")
    if not isinstance(a,dict) or set(a)!={"required_signals","min_expected_gain"}: raise ValidationError("malformed activation")
    sig=a["required_signals"]
    if not isinstance(sig,list) or not sig or sig!=sorted(set(sig)) or not all(isinstance(x,str) and x for x in sig): raise ValidationError("required_signals must be sorted unique strings")
    gain=a["min_expected_gain"]
    if isinstance(gain,bool) or not isinstance(gain,(int,float)) or not 0<=gain<=1: raise ValidationError("invalid min_expected_gain")
    b=d.get("budgets")
    if not isinstance(b,dict) or set(b)!=BUDGET_FIELDS: raise ValidationError("malformed budgets")
    for k,v in b.items():
        if isinstance(v,bool) or not isinstance(v,int) or v<1: raise ValidationError(f"invalid budget {k}")
    if b["max_model_nodes"]>b["max_nodes"]: raise ValidationError("incoherent budgets")
    nodes=d.get("nodes")
    if not isinstance(nodes,list) or not nodes: raise ValidationError("nodes required")
    ids=[]
    for n in nodes:
        if not isinstance(n,dict) or set(n)!={"id","type","scope","authority","uses_model","optional"}: raise ValidationError("malformed node")
        if not isinstance(n["id"],str) or not re.fullmatch(r"n_[A-Za-z0-9_-]{1,156}",n["id"]): raise ValidationError("invalid node id")
        if n["type"] not in NODE_TYPES or n["authority"] not in AUTHORITIES: raise ValidationError("invalid node semantics")
        if not isinstance(n["scope"],str) or not n["scope"].strip() or not isinstance(n["uses_model"],bool) or not isinstance(n["optional"],bool): raise ValidationError("invalid node fields")
        ids.append(n["id"])
    if len(ids)!=len(set(ids)): raise ValidationError("duplicate node id")
    if len(nodes)>b["max_nodes"] or sum(n["uses_model"] for n in nodes)>b["max_model_nodes"]: raise ValidationError("node budget exceeded")
    ids=set(ids); adj=defaultdict(list); indeg={i:0 for i in ids}
    controls=d.get("control_edges")
    reliance=d.get("reliance_edges")
    if not isinstance(controls,list) or not isinstance(reliance,list): raise ValidationError("edge lists required")
    cseen=set()
    for e in controls:
        if not isinstance(e,dict) or set(e)!={"from","to","relation","reason"}: raise ValidationError("malformed control edge")
        if e["from"] not in ids or e["to"] not in ids or e["from"]==e["to"] or e["relation"] not in CONTROL or not isinstance(e["reason"],str) or not e["reason"]: raise ValidationError("invalid control edge")
        key=(e["from"],e["to"],e["relation"])
        if key in cseen: raise ValidationError("duplicate control edge")
        cseen.add(key)
        if e["relation"] in DAG_CONTROL: adj[e["from"]].append(e["to"]); indeg[e["to"]]+=1
    q=deque(sorted(k for k,v in indeg.items() if v==0)); seen=0
    while q:
        cur=q.popleft(); seen+=1
        for nxt in sorted(adj[cur]):
            indeg[nxt]-=1
            if indeg[nxt]==0:q.append(nxt)
    if seen!=len(ids): raise ValidationError("control graph contains a cycle")
    rseen=set()
    for e in reliance:
        if not isinstance(e,dict) or set(e)!={"from","to","relation","source_grade","evidence_refs","reason"}: raise ValidationError("malformed reliance edge")
        if e["from"] not in ids or e["to"] not in ids or e["from"]==e["to"] or e["relation"] not in RELIANCE or e["source_grade"] not in GRADES: raise ValidationError("invalid reliance edge")
        if not isinstance(e["evidence_refs"],list) or e["evidence_refs"]!=sorted(set(e["evidence_refs"])) or not all(isinstance(x,str) and x for x in e["evidence_refs"]): raise ValidationError("invalid evidence_refs")
        if not isinstance(e["reason"],str) or not e["reason"]: raise ValidationError("invalid reliance reason")
        key=(e["from"],e["to"],e["relation"],e["source_grade"])
        if key in rseen: raise ValidationError("duplicate reliance edge")
        rseen.add(key)
    if len(controls)+len(reliance)>b["max_edges"]: raise ValidationError("edge budget exceeded")
    sc=d.get("stop_conditions")
    if not isinstance(sc,list) or not sc or sc!=sorted(set(sc)) or not all(isinstance(x,str) and x for x in sc): raise ValidationError("stop_conditions must be sorted unique strings")
    _validate_activation_profiles(d)
    return d

def validate_patterns(root: Path=ROOT):
    required={"id","description","allowed_operations","allowed_roles","allowed_join_policies","max_instances","required_operations"}
    paths=sorted((root/"graph"/"quality"/"patterns").glob("*.json"))
    if len(paths)!=6: raise ValidationError(f"expected exactly 6 quality patterns, found {len(paths)}")
    ids=set()
    for p in paths:
        d=load_json(p)
        if not isinstance(d,dict) or set(d)!=required: raise ValidationError(f"{p.name}: malformed quality pattern")
        if not isinstance(d["id"],str) or not d["id"] or d["id"] in ids: raise ValidationError(f"{p.name}: invalid/duplicate id")
        ids.add(d["id"])
        if not isinstance(d["description"],str) or not d["description"].strip(): raise ValidationError(f"{p.name}: invalid description")
        for k in ("allowed_operations","allowed_roles","allowed_join_policies","required_operations"):
            if not isinstance(d[k],list) or not d[k] or len(d[k])!=len(set(d[k])) or not all(isinstance(x,str) and x for x in d[k]): raise ValidationError(f"{p.name}: invalid {k}")
        try:
            unmatched=[op for op in d["required_operations"] if not any(re.fullmatch(pattern,op) for pattern in d["allowed_operations"])]
        except re.error as e:
            raise ValidationError(f"{p.name}: invalid allowed_operations regex: {e}")
        if unmatched: raise ValidationError(f"{p.name}: required_operations not covered by allowed_operations: {unmatched}")
        if isinstance(d["max_instances"],bool) or not isinstance(d["max_instances"],int) or d["max_instances"]<1: raise ValidationError(f"{p.name}: invalid max_instances")

def release_privacy_scan(root: Path=ROOT):
    forbidden_dirs={"__pycache__",".pytest_cache",".git"}
    forbidden_suffix={".pyc",".pyo",".p12",".pfx",".pem",".key"}
    forbidden_names={".env",".env.local",".env.production",".npmrc",".pypirc",".netrc",".git-credentials","credentials.json","service-account.json","id_rsa","id_ed25519"}
    text_rx=[
      re.compile(r"[A-Za-z]:[/\\]Users[/\\][^/\\\s]+",re.I),
      re.compile(r"/"+"Users/"+r"[^/\s]+"), re.compile(r"/"+"home/"+r"[^/\s]+"),
      re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
      re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{20,}|AIza[0-9A-Za-z_-]{30,})\b"),
    ]
    issues=[]
    for p in root.rglob("*"):
        rel=p.relative_to(root)
        if p.is_symlink(): issues.append(f"forbidden symlink: {rel}"); continue
        if any(part in forbidden_dirs for part in rel.parts): issues.append(f"forbidden path: {rel}"); continue
        if p.name.lower() in forbidden_names: issues.append(f"forbidden secret-bearing filename: {rel}"); continue
        if p.is_file() and p.suffix.lower() in forbidden_suffix: issues.append(f"forbidden file: {rel}"); continue
        if p.is_file() and p.stat().st_size<=2_000_000:
            try: text=p.read_text(encoding="utf-8")
            except (UnicodeDecodeError,OSError): continue
            for rx in text_rx:
                if rx.search(text): issues.append(f"privacy pattern {rx.pattern!r}: {rel}")
    return sorted(set(issues))


def _safe_release_rel(rel: str) -> bool:
    if not isinstance(rel,str) or not rel or "\\" in rel or "\x00" in rel:
        return False
    p=Path(rel)
    return not p.is_absolute() and rel == p.as_posix() and all(part not in {"", ".", ".."} for part in p.parts)

def verify_release_manifest(root: Path=ROOT):
    manifest_path=root/"MANIFEST.json"; sums_path=root/"CHECKSUMS.sha256"
    if not manifest_path.is_file() or not sums_path.is_file():
        raise ValidationError("release manifest/checksums missing")
    manifest=load_json(manifest_path)
    if (not isinstance(manifest,dict) or set(manifest)!={"schemaVersion","version","files"}
        or manifest.get("schemaVersion")!=1 or manifest.get("version")!=RELEASE_VERSION or not isinstance(manifest.get("files"),dict)):
        raise ValidationError("malformed MANIFEST.json")
    for rel,want in manifest["files"].items():
        if not _safe_release_rel(rel) or not isinstance(want,str) or not HEX64.fullmatch(want):
            raise ValidationError(f"unsafe/invalid MANIFEST.json entry: {rel!r}")
    excluded={"MANIFEST.json","CHECKSUMS.sha256"}
    actual={str(p.relative_to(root)).replace("\\","/") for p in root.rglob("*") if p.is_file() and not p.is_symlink() and not any(part in {"__pycache__",".pytest_cache",".git"} for part in p.relative_to(root).parts) and str(p.relative_to(root)).replace("\\","/") not in excluded}
    if set(manifest["files"])!=actual:
        missing=sorted(actual-set(manifest["files"])); extra=sorted(set(manifest["files"])-actual)
        raise ValidationError(f"manifest file set mismatch missing={missing} extra={extra}")
    for rel,want in manifest["files"].items():
        p=root/rel
        if p.is_symlink() or not p.is_file(): raise ValidationError(f"manifest payload missing/unsafe: {rel}")
        got=hashlib.sha256(p.read_bytes()).hexdigest()
        if got!=want: raise ValidationError(f"manifest hash mismatch: {rel}")
    declared={}
    for lineno,line in enumerate(sums_path.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip(): continue
        try: h,rel=line.split("  ",1)
        except ValueError: raise ValidationError(f"malformed CHECKSUMS.sha256 line {lineno}")
        if not HEX64.fullmatch(h) or not _safe_release_rel(rel): raise ValidationError(f"unsafe/invalid CHECKSUMS.sha256 line {lineno}")
        if rel in declared: raise ValidationError(f"duplicate CHECKSUMS.sha256 entry: {rel}")
        declared[rel]=h
    expected=dict(manifest["files"]); expected["MANIFEST.json"]=hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if declared!=expected: raise ValidationError("CHECKSUMS.sha256 does not exactly match manifest payload plus MANIFEST.json")
    return True

def _find_session_run(state_root: Path, run_id: str):
    if not RUN_ID.fullmatch(run_id): raise ValidationError("invalid run id")
    state_root=state_root.resolve(); sessions=state_root/"sessions"; matches=[]
    if sessions.is_symlink(): raise ValidationError("unsafe symlinked sessions directory")
    if sessions.exists() and not sessions.is_dir(): raise ValidationError("sessions path is not a directory")
    if sessions.is_dir():
        for session in sorted(sessions.iterdir()):
            if session.is_symlink(): raise ValidationError(f"unsafe symlinked session directory: {session.name}")
            if not session.is_dir() or not re.fullmatch(r"[0-9a-f]{64}",session.name): continue
            active=session/"active.json"
            if not active.exists(): continue
            if active.is_symlink() or not active.is_file(): raise ValidationError(f"unsafe active state file: {active}")
            try: d=load_json(active)
            except Exception as e: raise ValidationError(f"malformed active state file {active}: {e}")
            if not isinstance(d,dict): raise ValidationError(f"malformed active state object: {active}")
            if d.get("runId")==run_id: matches.append((active,d))
    if len(matches)!=1: raise ValidationError(f"expected exactly one session-scoped active run match, found {len(matches)}")
    return matches[0]

def candidate_review(state_root: Path, run_id: str):
    active,d=_find_session_run(state_root,run_id)
    path=active.parent/f"candidate-review-{run_id}.json"
    if path.is_symlink() or not path.is_file(): raise ValidationError("candidate review packet missing/unsafe")
    raw=path.read_bytes(); review=json.loads(raw.decode("utf-8"))
    expected_hash=d.get("candidateReviewHash")
    if not isinstance(expected_hash,str) or not HEX64.fullmatch(expected_hash) or hashlib.sha256(raw).hexdigest()!=expected_hash:
        raise ValidationError("candidate review packet hash does not match active state")
    staged=d.get("stagedActions")
    if not isinstance(staged,list) or not staged or any(not isinstance(x,dict) or set(x)!={"tool","actionHash"} or not isinstance(x.get("tool"),str) or not HEX64.fullmatch(str(x.get("actionHash",""))) for x in staged):
        raise ValidationError("active staged actions are malformed")
    expected_hashes=[x["actionHash"] for x in staged]
    if not isinstance(review,dict) or set(review)!={"schemaVersion","runId","candidateHash","actionHashes","actions"} or review.get("schemaVersion")!=1 or review.get("runId")!=run_id or review.get("candidateHash")!=d.get("candidateHash") or review.get("actionHashes")!=expected_hashes or not isinstance(review.get("actions"),list) or len(review["actions"])!=len(staged):
        raise ValidationError("candidate review packet is not bound to the active staged candidate")
    for row,want,staged_row in zip(review["actions"],expected_hashes,staged):
        if not isinstance(row,dict) or set(row)!={"tool_name","arguments"} or row.get("tool_name")!=staged_row["tool"] or not isinstance(row.get("tool_name"),str):
            raise ValidationError("candidate review action shape/tool mismatch")
        if stable_hash({"tool":row["tool_name"],"arguments":row["arguments"]})!=want:
            raise ValidationError("candidate review raw action does not match its sealed action hash")
    template_id=d.get("templateId"); template_hash=d.get("templateHash")
    if not isinstance(template_id,str) or not isinstance(template_hash,str) or not HEX64.fullmatch(template_hash):
        raise ValidationError("active state lacks candidate template binding")
    if stable_hash({"templateId":template_id,"templateHash":template_hash,"actions":staged})!=d.get("candidateHash"):
        raise ValidationError("candidate hash does not bind template and staged actions")
    return path,review

def recover_abort(state_root: Path, run_id: str):
    active,d=_find_session_run(state_root,run_id)
    session=active.parent
    archive=session/f"aborted-{run_id}.json"
    if archive.exists() or archive.is_symlink(): raise ValidationError("recovery archive already exists")
    review=session/f"candidate-review-{run_id}.json"; approval=session/f"approval-{run_id}.json"
    for p in (review,approval):
        if p.is_symlink(): raise ValidationError(f"unsafe symlinked recovery artifact: {p.name}")
    # Raw candidate/approval material is removed before the active state is archived.
    # If the process stops between these steps the run remains fail-closed and this
    # command can be safely retried; no pending tool call is ever automatically replayed.
    for p in (review,approval):
        if p.exists():
            if not p.is_file(): raise ValidationError(f"unsafe recovery artifact: {p.name}")
            p.unlink()
    os.replace(active,archive)
    return archive

def approve(state_root: Path, run_id: str, candidate_hash: str):
    if not HEX64.fullmatch(candidate_hash): raise ValidationError("candidate hash must be 64 lowercase hex chars")
    active,d=_find_session_run(state_root,run_id)
    if d.get("currentNode")!="n_approval" or d.get("closed"): raise ValidationError("approval is only valid for the active run at n_approval")
    if d.get("candidateHash")!=candidate_hash: raise ValidationError("candidate hash does not match active staged candidate")
    if d.get("approvedCandidateHash") is not None: raise ValidationError("candidate is already approved")
    candidate_review(state_root,run_id)
    token={"schemaVersion":3,"runId":run_id,"candidateHash":candidate_hash}
    path=active.parent/f"approval-{run_id}.json"
    if path.is_symlink(): raise ValidationError("unsafe symlinked approval token path")
    raw=json.dumps(token,sort_keys=True,separators=(",",":"))+"\n"
    tmp_path=None
    try:
        with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=str(active.parent),prefix=f".approval-{run_id}-",suffix=".tmp",delete=False) as f:
            tmp_path=Path(f.name); f.write(raw); f.flush(); os.fsync(f.fileno())
        try: os.chmod(tmp_path,0o600)
        except OSError: pass
        os.replace(tmp_path,path)
    finally:
        if tmp_path is not None and tmp_path.exists():
            try: tmp_path.unlink()
            except OSError: pass
    return path

def cmd_selftest(root: Path):
    failures=[]
    files=template_files(root)
    if len(files)!=10: failures.append(f"expected 10 executable graph templates, found {len(files)}")
    for p in files:
        try: validate_template(load_json(p))
        except Exception as e: failures.append(f"{p.relative_to(root)}: {e}")
    try: validate_patterns(root)
    except Exception as e: failures.append(str(e))
    issues=release_privacy_scan(root)
    failures.extend(issues)
    try: verify_release_manifest(root)
    except Exception as e: failures.append(str(e))
    if failures:
        for x in failures: print("FAIL",x)
        return 1
    print(f"PASS templates={len(files)} quality_patterns=6 privacy=clean")
    return 0

def main(argv=None):
    ap=argparse.ArgumentParser(prog="graphleanctl")
    sp=ap.add_subparsers(dest="cmd",required=True)
    p=sp.add_parser("validate"); p.add_argument("path",nargs="?")
    sp.add_parser("list")
    p=sp.add_parser("selftest"); p.add_argument("--root",default=str(ROOT))
    p=sp.add_parser("approve"); p.add_argument("--state-root",required=True); p.add_argument("--run",required=True); p.add_argument("--candidate-hash",required=True)
    p=sp.add_parser("candidate-show"); p.add_argument("--state-root",required=True); p.add_argument("--run",required=True)
    p=sp.add_parser("recover-abort"); p.add_argument("--state-root",required=True); p.add_argument("--run",required=True)
    args=ap.parse_args(argv)
    try:
        if args.cmd=="list":
            for p in template_files(ROOT):
                d=validate_template(load_json(p)); print(d["template_id"],d["version"],p.relative_to(ROOT))
            return 0
        if args.cmd=="validate":
            paths=[Path(args.path)] if args.path else template_files(ROOT)
            for p in paths:
                d=validate_template(load_json(p)); print("PASS",p,stable_hash(d))
            return 0
        if args.cmd=="selftest": return cmd_selftest(Path(args.root).resolve())
        if args.cmd=="approve":
            print(approve(Path(args.state_root).expanduser().resolve(),args.run,args.candidate_hash)); return 0
        if args.cmd=="candidate-show":
            _path,review=candidate_review(Path(args.state_root).expanduser().resolve(),args.run); print(json.dumps(review,ensure_ascii=False,indent=2)); return 0
        if args.cmd=="recover-abort":
            print(recover_abort(Path(args.state_root).expanduser().resolve(),args.run)); return 0
    except Exception as e:
        print(f"ERROR: {e}",file=sys.stderr); return 2
    return 2
if __name__=="__main__": raise SystemExit(main())

