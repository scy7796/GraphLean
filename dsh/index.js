import { appendFileSync, existsSync, mkdirSync, readFileSync, realpathSync, renameSync, unlinkSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHash, randomBytes } from 'node:crypto'
import { serialize } from 'node:v8'

export const name = 'graphlean-gate'
export const inject = ['tools']

const ROOT = dirname(fileURLToPath(import.meta.url))
const GRAPH_ROOT = existsSync(join(ROOT, 'graph')) ? join(ROOT, 'graph') : join(dirname(ROOT), 'graph')
const INSTALLER_META = '.graphlean-installer-v1.0.1'
const CONTROL_TOOLS = new Set(['graphlean_begin', 'graphlean_status', 'graphlean_stage_candidate', 'graphlean_advance', 'graphlean_abort'])
const TRANSPORT_TOOLS = new Set([])
const READ_ONLY_TOOLS = new Set([
  'read', 'read_image', 'glob', 'grep', 'lsp',
  'terminal_list', 'terminal_read', 'job_list', 'job_output',
  'get_goal', 'schedule_list', 'session_event_read', 'session_event_search', 'session_event_trace',
  'session_search', 'session_trace', 'list_agents',
])
const WORKSPACE_WRITE_TOOLS = new Set(['edit', 'write'])
const USER_INTERACTION_TOOLS = new Set(['ask_user_question', 'exit_plan_mode'])
const EXTERNAL_ACTION_TOOLS = new Set([
  'web_fetch', 'web_search', 'create_goal', 'update_goal', 'schedule_create', 'schedule_delete',
  'subagent', 'subagent_fork', 'interrupt_agent', 'send_message', 'report', 'job_kill', 'todo_write',
])
const HARD_DENY_TOOLS = new Set(['run_code', 'bash', 'pwsh', 'terminal_open', 'terminal_send', 'terminal_signal', 'terminal_close', 'cordis_define', 'cordis_inspect_list', 'cordis_inspect_query', 'cordis_inspect_self', 'cordis_run', 'cordis_stop', 'cordis_undefine', 'workflow', 'ralph', 'skill'])
const CONTROL_RELATIONS = new Set(['precedes', 'verifies'])

function dshHome(config = {}) {
  const parent = dirname(ROOT)
  if (basename(ROOT) === 'plugin' && basename(parent) === 'graphlean') return dirname(parent)
  return process.env.DSH_HOME ? resolve(process.env.DSH_HOME) : join(homedir(), '.dsh')
}
function stateRoot(config) { return config?.stateRoot || join(dshHome(config), 'graphlean', 'state') }
function now() { return new Date().toISOString() }
function canonical(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`
  return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`
}
function sha(value) { return createHash('sha256').update(canonical(value)).digest('hex') }
function shaText(value) { return createHash('sha256').update(value).digest('hex') }
function hashOpaque(value) {
  try { return createHash('sha256').update(serialize(value)).digest('hex') }
  catch { return shaText(`unserializable:${typeof value}`) }
}
function agentKey(exec) {
  const id = exec?.agent?.id
  const sessionId = exec?.agent?.session?.header?.id
  if (id === undefined || id === null || String(id).length === 0) throw new Error('GraphLean requires an initiating DSH agent')
  if (sessionId === undefined || sessionId === null || String(sessionId).length === 0) throw new Error('GraphLean requires the initiating DSH session header id')
  return shaText(`${String(id)}\0${String(sessionId)}`)
}
function sessionDir(config, exec) { return join(stateRoot(config), 'sessions', agentKey(exec)) }
function activePath(config, exec) { return join(sessionDir(config, exec), 'active.json') }
function receiptsPath(config, exec) { return join(sessionDir(config, exec), 'receipts.jsonl') }
function approvalPath(config, exec, runId) { return join(sessionDir(config, exec), `approval-${runId}.json`) }
function candidateReviewPath(config, exec, runId) { return join(sessionDir(config, exec), `candidate-review-${runId}.json`) }
function atomicJson(path, value) {
  mkdirSync(dirname(path), { recursive: true, mode: 0o700 })
  const tmp = `${path}.tmp-${process.pid}-${randomBytes(4).toString('hex')}`
  writeFileSync(tmp, JSON.stringify(value, null, 2) + '\n', { encoding: 'utf8', mode: 0o600 })
  renameSync(tmp, path)
}
function readJson(path) { return JSON.parse(readFileSync(path, 'utf8')) }
function safeUnlink(path) { try { if (existsSync(path)) unlinkSync(path) } catch {} }
function readActive(config, exec) {
  const p = activePath(config, exec); if (!existsSync(p)) return null
  return readJson(p) // pure read: never derive destructive paths from unvalidated state
}
function cleanupApprovedArtifacts(config, exec, state) {
  if (state.candidateHash && state.approvedCandidateHash === state.candidateHash) {
    safeUnlink(candidateReviewPath(config, exec, state.runId)); safeUnlink(approvalPath(config, exec, state.runId))
  }
}
function templatePaths() {
  return [
    join(GRAPH_ROOT, 'templates', 'adaptive-execution.json'), join(GRAPH_ROOT, 'templates', 'evidence-audit.json'),
    join(GRAPH_ROOT, 'templates', 'evidence-research.json'), join(GRAPH_ROOT, 'templates', 'hypothesis-diagnosis.json'),
    join(GRAPH_ROOT, 'templates', 'inline-advised.json'), join(GRAPH_ROOT, 'templates', 'inline-micro.json'),
    join(GRAPH_ROOT, 'templates', 'multi-artifact.json'), join(GRAPH_ROOT, 'templates', 'work-dag.json'),
    join(GRAPH_ROOT, 'quality', 'quality-improvement.json'), join(GRAPH_ROOT, 'evolution', 'self-evolution.json'),
  ]
}
function templates() {
  const out = new Map()
  for (const p of templatePaths()) { const d = readJson(p); out.set(d.template_id, d) }
  return out
}
function graphHash(template) { return sha(template) }
function nodeById(template, id) { const n = template.nodes.find(n => n.id === id); if (!n) throw new Error(`unknown graph node ${id}`); return n }
function allPredecessors(template, nodeId) {
  return template.control_edges.filter(e => CONTROL_RELATIONS.has(e.relation) && e.to === nodeId).map(e => e.from)
}
function readyNodes(template, state) {
  const active = new Set(state.activeNodes)
  const completed = new Set(state.completed)
  return state.activeNodes.filter(id => !completed.has(id) && allPredecessors(template, id).filter(p => active.has(p)).every(p => completed.has(p))).sort()
}
function deterministicSchedule(template, activeNodes) {
  const active = new Set(activeNodes); const completed = new Set(); const out = []
  while (out.length < activeNodes.length) {
    const ready = [...active].filter(id => !completed.has(id) && allPredecessors(template, id).filter(p => active.has(p)).every(p => completed.has(p))).sort()
    if (!ready.length) throw new Error('GraphLean active graph has no deterministic topological schedule')
    const next = ready[0]; out.push(next); completed.add(next)
  }
  return out
}
function optionalComponents(template) {
  const optionals = new Set(template.nodes.filter(n => n.optional).map(n => n.id))
  const adj = new Map([...optionals].map(id => [id, new Set()]))
  for (const edge of template.control_edges) {
    if (optionals.has(edge.from) && optionals.has(edge.to)) { adj.get(edge.from).add(edge.to); adj.get(edge.to).add(edge.from) }
  }
  const seen = new Set(); const components = []
  for (const start of [...optionals].sort()) {
    if (seen.has(start)) continue
    const stack = [start]; const component = []
    while (stack.length) {
      const cur = stack.pop(); if (seen.has(cur)) continue
      seen.add(cur); component.push(cur)
      for (const next of [...adj.get(cur)].sort().reverse()) if (!seen.has(next)) stack.push(next)
    }
    components.push(component.sort())
  }
  return components
}
function normalizeSelectedOptional(template, selected) {
  const optionals = new Set(template.nodes.filter(n => n.optional).map(n => n.id))
  const requested = [...new Set(selected ?? [])].sort()
  for (const id of requested) if (!optionals.has(id)) throw new Error(`optional_nodes contains non-optional/unknown node: ${id}`)
  const requestSet = new Set(requested); const expanded = new Set()
  for (const component of optionalComponents(template)) if (component.some(id => requestSet.has(id))) for (const id of component) expanded.add(id)
  return [...expanded].sort()
}
function validateConfig(config) {
  if (!isPlainObject(config)) throw new Error('GraphLean config must be an object')
  const allowedKeys = new Set(['readOnlyTools','workspaceWriteTools','externalActionTools','stateRoot','requireActivationApproval'])
  for (const key of Object.keys(config)) if (!allowedKeys.has(key)) throw new Error(`unknown GraphLean config key: ${key}`)
  const buckets = [['readOnlyTools','read_only'], ['workspaceWriteTools','workspace_write'], ['externalActionTools','external_action']]
  const seen = new Map()
  const fixedBuiltins = new Set([...CONTROL_TOOLS, ...HARD_DENY_TOOLS, ...READ_ONLY_TOOLS, ...WORKSPACE_WRITE_TOOLS, ...USER_INTERACTION_TOOLS, ...EXTERNAL_ACTION_TOOLS, 'str_replace_editor'])
  for (const [key, effect] of buckets) {
    const value = config?.[key]
    if (value === undefined) continue
    if (!Array.isArray(value) || value.some(x => typeof x !== 'string' || !x) || new Set(value).size !== value.length) throw new Error(`GraphLean config ${key} must be a unique array of non-empty tool names`)
    for (const name of value) {
      if (fixedBuiltins.has(name)) throw new Error(`GraphLean config cannot reclassify built-in/protected tool ${name}`)
      if (seen.has(name)) throw new Error(`GraphLean config assigns ${name} to multiple effects`)
      seen.set(name, effect)
    }
  }
  if (config?.stateRoot !== undefined && (typeof config.stateRoot !== 'string' || !isAbsolute(config.stateRoot))) throw new Error('GraphLean config stateRoot must be an absolute path')
  if (config?.requireActivationApproval !== undefined && typeof config.requireActivationApproval !== 'boolean') throw new Error('GraphLean config requireActivationApproval must be boolean')
}
function classify(name, args, config) {
  if (CONTROL_TOOLS.has(name)) return 'control'
  if (HARD_DENY_TOOLS.has(name)) return 'hard_deny'
  if (TRANSPORT_TOOLS.has(name)) return 'transport'
  if (USER_INTERACTION_TOOLS.has(name)) return 'user_interaction'
  if (Array.isArray(config?.externalActionTools) && config.externalActionTools.includes(name)) return 'external_action'
  if (Array.isArray(config?.workspaceWriteTools) && config.workspaceWriteTools.includes(name)) return 'workspace_write'
  if (Array.isArray(config?.readOnlyTools) && config.readOnlyTools.includes(name)) return 'read_only'
  if (name === 'str_replace_editor') return args?.command === 'view' ? 'read_only' : ['create', 'str_replace', 'insert'].includes(args?.command) ? 'workspace_write' : 'unclassified'
  if (READ_ONLY_TOOLS.has(name)) return 'read_only'
  if (WORKSPACE_WRITE_TOOLS.has(name)) return 'workspace_write'
  if (EXTERNAL_ACTION_TOOLS.has(name)) return 'external_action'
  return 'unclassified' // unknown bounded tools require an explicit administrator classification
}
function actionHash(name, args) { return sha({ tool: name, arguments: args }) }
function executionKey(exec) {
  if (exec?.callId === undefined || exec?.callId === null || String(exec.callId).length === 0) throw new Error('GraphLean requires DSH ToolExecution.callId for budget reservation')
  return shaText(String(exec.callId))
}
function isWithin(parent, child) {
  const rel = relative(parent, child)
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel))
}
function resolveThroughExistingPrefix(value) {
  let target = resolve(value); let cursor = target; const tail = []
  while (!existsSync(cursor)) {
    const parent = dirname(cursor); if (parent === cursor) return target
    tail.unshift(basename(cursor)); cursor = parent
  }
  try { return resolve(realpathSync(cursor), ...tail) } catch { return target }
}
function sessionCwd(exec) {
  const cwd = exec?.agent?.session?.header?.cwd
  return typeof cwd === 'string' && cwd ? resolve(cwd) : null
}
function accessTarget(name, args, exec) {
  if (name === 'read' || name === 'read_image' || name === 'write' || name === 'edit' || name === 'lsp') return typeof args?.file_path === 'string' ? args.file_path : null
  if (name === 'str_replace_editor') return typeof args?.path === 'string' ? args.path : null
  if (name === 'glob' || name === 'grep') {
    if (typeof args?.path === 'string' && args.path) return args.path
    return sessionCwd(exec)
  }
  return null
}
function resolveToolPath(raw, exec) {
  if (isAbsolute(raw)) return resolve(raw)
  const cwd = sessionCwd(exec)
  return cwd ? resolve(cwd, raw) : null
}
function protectedAccessReason(name, args, config, exec) {
  const fsTools = new Set(['read','read_image','write','edit','lsp','str_replace_editor','glob','grep'])
  if (!fsTools.has(name)) return null
  const cwd = sessionCwd(exec)
  if (!cwd) return 'GraphLean denies filesystem access without a trusted DSH session workspace cwd.'
  if ((name === 'write' || name === 'edit') && (args?.sandbox_permissions !== undefined || args?.justification !== undefined)) return 'GraphLean hard governance denies filesystem sandbox-escalation arguments.'
  const raw = accessTarget(name, args, exec)
  if (raw === null) {
    if (name === 'glob' || name === 'grep') {
      // Omitted discovery path means the exact DSH session workspace.
    } else return 'GraphLean denies filesystem access without an explicit path.'
  }
  const lexical = raw === null ? cwd : resolveToolPath(raw, exec)
  if (lexical === null) return `GraphLean denies ambiguous relative filesystem path without a trusted DSH session cwd: ${raw}`
  const canonicalPath = resolveThroughExistingPrefix(lexical)
  const workspaceLexical = resolve(cwd); const workspaceCanonical = resolveThroughExistingPrefix(workspaceLexical)
  if (!isWithin(workspaceLexical, lexical) || !isWithin(workspaceCanonical, canonicalPath)) return `GraphLean denies filesystem access outside the DSH session workspace: ${raw ?? cwd}`
  const hostHome = resolve(dshHome(config))
  // DSH_HOME is a host control plane, not workspace data. Protect it wholesale so
  // a broad session cwd (for example the user's home directory) cannot expose
  // Harness configuration, sessions, provider state, or GraphLean internals.
  const protectedRoots = [...new Set([hostHome, resolve(stateRoot(config))])]
  const protectedCandidates = protectedRoots.flatMap(x => [x, resolveThroughExistingPrefix(x)])
  const isDiscovery = name === 'glob' || name === 'grep'
  for (const target of [lexical, canonicalPath]) {
    for (const protectedPath of protectedCandidates) {
      const direct = isWithin(protectedPath, target)
      const containsProtected = isDiscovery && isWithin(target, protectedPath)
      if (direct || containsProtected) return `GraphLean control-plane path is inaccessible to governed tools: ${raw ?? cwd}`
    }
  }
  return null
}

function runExpired(state, template) {
  const start = Date.parse(state.startedAt); return !Number.isFinite(start) || Date.now() - start > template.budgets.max_total_latency_ms
}
function reserveCall(config, exec, state, template, effect) {
  const key = executionKey(exec); const pending = Array.isArray(state.pendingCalls) ? state.pendingCalls : []
  if (pending.some(x => x.callKey === key)) return 'GraphLean duplicate execution reservation denied.'
  if ((state.toolCallCount ?? 0) + pending.length >= template.budgets.max_tool_calls) return `GraphLean tool-call budget exhausted (${template.budgets.max_tool_calls}).`
  if (pending.length >= template.budgets.max_parallel_calls) return `GraphLean parallel-call budget exhausted (${template.budgets.max_parallel_calls}).`
  pending.push({ callKey: key, nodeId: state.currentNode, tool: exec.name, effect, actionHash: actionHash(exec.name, exec.arguments), argsHash: sha(exec.arguments) })
  state.pendingCalls = pending; atomicJson(activePath(config, exec), state); return undefined
}
function safeState(state, template = null) {
  if (!state) return { active: false }
  const ready = state.closed || !template ? [] : readyNodes(template, state)
  return {
    active: true, runId: state.runId, templateId: state.templateId, templateHash: state.templateHash,
    currentNode: state.currentNode, completed: [...state.completed], readyNodes: ready,
    selectedOptionalNodes: [...(state.selectedOptionalNodes ?? [])], skippedOptionalNodes: [...(state.skippedOptionalNodes ?? [])],
    candidateHash: state.candidateHash || null, candidateReviewHash: state.candidateReviewHash || null, approvedCandidateHash: state.approvedCandidateHash || null,
    stagedActionCount: Array.isArray(state.stagedActions) ? state.stagedActions.length : 0,
    toolCallCount: state.toolCallCount ?? 0, pendingCallCount: Array.isArray(state.pendingCalls) ? state.pendingCalls.length : 0, closed: !!state.closed,
  }
}
function renderJson(_args, value) { return [{ type: 'text', text: JSON.stringify(value) }] }
function jsonOutput() { return { schema: {}, render: renderJson } }
function isPlainObject(value) { return value !== null && typeof value === 'object' && !Array.isArray(value) }
function assertExactObject(value, allowed, required = []) {
  if (!isPlainObject(value)) throw new Error('tool arguments must be a JSON object')
  for (const key of Object.keys(value)) if (!allowed.includes(key)) throw new Error(`unexpected argument: ${key}`)
  for (const key of required) if (!(key in value)) throw new Error(`missing required argument: ${key}`)
}
function validateBeginArgs(args) {
  assertExactObject(args, ['template_id', 'optional_nodes'], ['template_id'])
  if (typeof args.template_id !== 'string' || !args.template_id) throw new Error('template_id must be a non-empty string')
  if ('optional_nodes' in args && (!Array.isArray(args.optional_nodes) || args.optional_nodes.some(x => typeof x !== 'string' || !x))) throw new Error('optional_nodes must be an array of non-empty strings')
}
function validateNoArgs(args) { assertExactObject(args ?? {}, []) }
function validateStageArgs(args) {
  assertExactObject(args, ['actions'], ['actions'])
  if (!Array.isArray(args.actions) || args.actions.length < 1 || args.actions.length > 32) throw new Error('candidate requires 1..32 actions')
  for (const action of args.actions) {
    assertExactObject(action, ['tool_name', 'arguments'], ['tool_name', 'arguments'])
    if (typeof action.tool_name !== 'string' || !action.tool_name) throw new Error('candidate action tool_name must be a non-empty string')
    if (action.arguments === undefined) throw new Error('candidate action arguments are required')
  }
}
function receiptRows(config, exec) {
  const p = receiptsPath(config, exec)
  if (!existsSync(p)) return []
  const rows = []
  for (const [i, line] of readFileSync(p, 'utf8').split(/\r?\n/).filter(Boolean).entries()) {
    let r; try { r = JSON.parse(line) } catch { throw new Error(`malformed GraphLean receipt JSON at line ${i + 1}`) }
    const keys = ['schemaVersion','time','runId','nodeId','tool','effect','actionHash','argsHash','isError','resultHash']
    if (!isPlainObject(r) || Object.keys(r).sort().join(',') !== keys.sort().join(',') || r.schemaVersion !== 3 || !/^run_[0-9a-f]{24}$/.test(r.runId) || typeof r.nodeId !== 'string' || typeof r.tool !== 'string' || !['read_only','workspace_write','external_action','user_interaction'].includes(r.effect) || !/^[0-9a-f]{64}$/.test(r.actionHash) || !/^[0-9a-f]{64}$/.test(r.argsHash) || !/^[0-9a-f]{64}$/.test(r.resultHash) || typeof r.isError !== 'boolean' || typeof r.time !== 'string' || Number.isNaN(Date.parse(r.time))) throw new Error(`malformed GraphLean receipt at line ${i + 1}`)
    rows.push(r)
  }
  return rows
}
function successfulReceiptSince(config, exec, state, requiredEffect) {
  for (const r of receiptRows(config, exec).reverse()) {
    if (r.runId !== state.runId || r.nodeId !== state.currentNode) continue
    if (r.time < state.enteredAt) break
    if (!r.isError && r.effect === requiredEffect) return true
  }
  return false
}
function successfulActionHashes(config, exec, state) {
  const out = new Set()
  for (const r of receiptRows(config, exec)) {
    if (r.runId === state.runId && r.nodeId === 'n_apply' && r.time >= state.enteredAt && !r.isError && r.actionHash) out.add(r.actionHash)
  }
  return out
}
function activationSpec(args) {
  validateBeginArgs(args)
  const template = templates().get(args.template_id); if (!template) return null
  const selected = normalizeSelectedOptional(template, args.optional_nodes); const set = new Set(selected)
  const active = template.nodes.filter(n => !n.optional || set.has(n.id))
  const privileged = [...new Set(active.map(n => n.authority).filter(a => a !== 'read_only'))].sort()
  return { template, selected, privileged, argsHash: sha(args) }
}
function validateState(state, template) {
  const required = ['schemaVersion','runId','templateId','templateHash','currentNode','activeNodes','selectedOptionalNodes','skippedOptionalNodes','completed','startedAt','enteredAt','candidateHash','candidateReviewHash','approvedCandidateHash','stagedActions','toolCallCount','pendingCalls','closed']
  const allowed = new Set([...required,'stagedAt','approvedAt'])
  if (!isPlainObject(state) || state.schemaVersion !== 3 || Object.keys(state).some(k => !allowed.has(k)) || required.some(k => !(k in state))) throw new Error('malformed GraphLean state')
  if (!/^run_[0-9a-f]{24}$/.test(state.runId) || state.templateId !== template.template_id || !/^[0-9a-f]{64}$/.test(state.templateHash)) throw new Error('invalid GraphLean state identity')
  if (!Array.isArray(state.activeNodes) || !Array.isArray(state.selectedOptionalNodes) || !Array.isArray(state.skippedOptionalNodes) || !Array.isArray(state.completed) || !Array.isArray(state.stagedActions) || !Array.isArray(state.pendingCalls)) throw new Error('invalid GraphLean state arrays')
  const unique = arr => arr.length === new Set(arr).size
  if (![state.activeNodes,state.selectedOptionalNodes,state.skippedOptionalNodes,state.completed].every(a => unique(a) && a.every(x => typeof x === 'string'))) throw new Error('invalid GraphLean state node sets')
  const optional = template.nodes.filter(n => n.optional).map(n => n.id).sort(); const selected = [...state.selectedOptionalNodes].sort(); const skipped = [...state.skippedOptionalNodes].sort()
  if (canonical(normalizeSelectedOptional(template, selected)) !== canonical(selected)) throw new Error('GraphLean selected optional nodes are not complete branch bundles')
  const expectedActive = template.nodes.filter(n => !n.optional || selected.includes(n.id)).map(n => n.id).sort()
  const expectedSkipped = optional.filter(id => !selected.includes(id)).sort()
  if (canonical([...state.activeNodes].sort()) !== canonical(expectedActive) || canonical(skipped) !== canonical(expectedSkipped) || selected.some(id => !optional.includes(id))) throw new Error('GraphLean active/optional node set mismatch')
  if (typeof state.currentNode !== 'string' || !state.activeNodes.includes(state.currentNode) || state.completed.some(id => !state.activeNodes.includes(id))) throw new Error('invalid GraphLean current/completed nodes')
  if (typeof state.startedAt !== 'string' || Number.isNaN(Date.parse(state.startedAt)) || typeof state.enteredAt !== 'string' || Number.isNaN(Date.parse(state.enteredAt)) || ('stagedAt' in state && (typeof state.stagedAt !== 'string' || Number.isNaN(Date.parse(state.stagedAt)))) || ('approvedAt' in state && (typeof state.approvedAt !== 'string' || Number.isNaN(Date.parse(state.approvedAt)))) ) throw new Error('invalid GraphLean state timestamp')
  if (!Number.isSafeInteger(state.toolCallCount) || state.toolCallCount < 0 || typeof state.closed !== 'boolean') throw new Error('invalid GraphLean state counters')
  for (const key of ['candidateHash','candidateReviewHash','approvedCandidateHash']) if (state[key] !== null && (typeof state[key] !== 'string' || !/^[0-9a-f]{64}$/.test(state[key]))) throw new Error(`invalid ${key}`)
  if (state.approvedCandidateHash !== null && state.approvedCandidateHash !== state.candidateHash) throw new Error('approved candidate hash mismatch')
  for (const a of state.stagedActions) if (!isPlainObject(a) || Object.keys(a).sort().join(',') !== 'actionHash,tool' || typeof a.tool !== 'string' || !/^[0-9a-f]{64}$/.test(a.actionHash)) throw new Error('invalid staged action')
  if (state.candidateHash !== null) {
    const expected = sha({ templateId: state.templateId, templateHash: state.templateHash, actions: state.stagedActions })
    if (expected !== state.candidateHash) throw new Error('candidate hash does not bind staged actions')
    if (state.candidateReviewHash === null) throw new Error('candidate hash exists without candidate review hash')
  } else if (state.stagedActions.length || state.candidateReviewHash !== null) throw new Error('staged candidate material exists without candidate hash')
  const pendingKeys = new Set()
  for (const x of state.pendingCalls) {
    if (!isPlainObject(x) || Object.keys(x).sort().join(',') !== 'actionHash,argsHash,callKey,effect,nodeId,tool' || !/^[0-9a-f]{64}$/.test(x.callKey) || !/^[0-9a-f]{64}$/.test(x.actionHash) || !/^[0-9a-f]{64}$/.test(x.argsHash) || typeof x.tool !== 'string' || !x.tool || x.nodeId !== state.currentNode || !['read_only','workspace_write','external_action','user_interaction'].includes(x.effect) || pendingKeys.has(x.callKey)) throw new Error('invalid pending call reservation')
    pendingKeys.add(x.callKey)
  }
  if (state.pendingCalls.length > template.budgets.max_parallel_calls || state.toolCallCount + state.pendingCalls.length > template.budgets.max_tool_calls) throw new Error('GraphLean persisted budget invariant violated')
  const schedule = deterministicSchedule(template, state.activeNodes)
  if (canonical(state.completed) !== canonical(schedule.slice(0, state.completed.length))) throw new Error('GraphLean completed nodes are not the deterministic schedule prefix')
  if (state.closed) {
    if (state.completed.length !== state.activeNodes.length || state.pendingCalls.length || state.currentNode !== schedule[schedule.length - 1]) throw new Error('closed GraphLean state is incomplete')
  } else {
    if (state.completed.length >= schedule.length || state.currentNode !== schedule[state.completed.length]) throw new Error('current GraphLean node is not the deterministic next node')
  }
}
function verifiedTemplateForState(state) {
  const template = templates().get(state.templateId)
  if (!template || graphHash(template) !== state.templateHash) throw new Error('GraphLean template integrity mismatch')
  validateState(state,template); return template
}

export function apply(ctx, config = {}) {
  validateConfig(config)
  const activationTickets = new Map()
  const ACTIVATION_TICKET_MS = 15 * 60 * 1000
  function pruneActivationTickets() {
    const cutoff = Date.now() - ACTIVATION_TICKET_MS
    for (const [token, ticket] of activationTickets) if (ticket.createdAt < cutoff) activationTickets.delete(token)
    while (activationTickets.size > 1024) activationTickets.delete(activationTickets.keys().next().value)
  }
  // The reorderable approval axis asks the user, but it is not itself the hard boundary.
  // It mints an in-memory ticket bound to this exact DSH ToolExecution token + arguments.
  // The monotonic guard below must consume the ticket; if another plugin bypasses this
  // listener, privileged graph activation still fails closed.
  ctx.on('tools/pre-execute', async (exec, next) => {
    if (exec.name !== 'graphlean_begin' || config?.requireActivationApproval === false) return next()
    let spec
    try { spec = activationSpec(exec.arguments) } catch { return next() }
    if (!spec || !spec.privileged.length) return next()
    if (typeof exec.token !== 'symbol') return { kind: 'deny', reason: 'GraphLean cannot bind privileged activation approval without the DSH ToolExecution token.' }
    pruneActivationTickets()
    activationTickets.set(exec.token, { createdAt: Date.now(), argsHash: spec.argsHash, templateHash: graphHash(spec.template) })
    const optional = spec.selected.length ? `; optional nodes: ${spec.selected.join(', ')}` : '; no optional nodes selected'
    return { kind: 'ask', reason: `Start GraphLean ${spec.template.template_id} (${graphHash(spec.template).slice(0,12)}) with host-governed authorities: ${spec.privileged.join(', ')}${optional}?` }
  })
  // Monotonic hard gate: a denial returned here cannot be undone by later policy listeners.
  ctx.tools.guard((exec) => {
    if (exec.name === 'graphlean_begin') {
      let spec
      try { spec = activationSpec(exec.arguments) } catch { return undefined } // body performs exact validation and will fail
      if (!spec || !spec.privileged.length || config?.requireActivationApproval === false) return undefined
      pruneActivationTickets()
      const ticket = typeof exec.token === 'symbol' ? activationTickets.get(exec.token) : null
      if (typeof exec.token === 'symbol') activationTickets.delete(exec.token) // one-shot, even on mismatch
      if (!ticket || Date.now() - ticket.createdAt > ACTIVATION_TICKET_MS || ticket.argsHash !== spec.argsHash || ticket.templateHash !== graphHash(spec.template)) return 'GraphLean privileged graph activation lacks a matching host approval ticket; denied fail-closed.'
      return undefined
    }
    const effect = classify(exec.name, exec.arguments, config)
    if (effect === 'control') return undefined
    if (effect === 'hard_deny') return `GraphLean hard-denies unbounded/composite tool ${exec.name}; it cannot be reclassified while hard governance is active.`
    if (effect === 'unclassified') return `GraphLean denies unclassified tool ${exec.name}; classify only bounded tools explicitly in plugin config before use.`
    const protectedReason = protectedAccessReason(exec.name, exec.arguments, config, exec); if (protectedReason) return protectedReason
    let state = null
    try { state = readActive(config, exec) } catch { return 'GraphLean state/agent identity is unreadable; non-control tool denied fail-closed.' }
    if (!state || state.closed) {
      if (effect === 'read_only' || effect === 'user_interaction') return undefined
      return `GraphLean requires an active graph before ${effect} tool ${exec.name}. Call graphlean_begin first.`
    }
    let template
    try { template = verifiedTemplateForState(state) } catch { return 'GraphLean state/template integrity mismatch; tool denied fail-closed.' }
    cleanupApprovedArtifacts(config, exec, state)
    if (runExpired(state, template)) return `GraphLean run exceeded max_total_latency_ms=${template.budgets.max_total_latency_ms}; abort or start a new approved run.`
    if (effect === 'read_only' || effect === 'user_interaction') return reserveCall(config, exec, state, template, effect)
    const node = nodeById(template, state.currentNode)
    if (node.type === 'verifier' || node.type === 'approval') return `GraphLean node ${node.id} is non-mutating; ${exec.name} denied.`
    const allowedEffects = node.authority === 'workspace_write' ? new Set(['read_only','workspace_write']) : node.authority === 'external_action' ? new Set(['read_only','external_action']) : new Set(['read_only'])
    if (!allowedEffects.has(effect)) return `GraphLean node ${node.id} authority ${node.authority} cannot execute ${effect} tool ${exec.name}.`
    if (state.templateId === 'gt_self_evolution' && state.currentNode === 'n_apply') {
      if (!state.candidateHash || state.approvedCandidateHash !== state.candidateHash) return 'Self-evolution candidate has not been approved for exact apply.'
      const h = actionHash(exec.name, exec.arguments)
      if (!Array.isArray(state.stagedActions) || !state.stagedActions.some(a => a.tool === exec.name && a.actionHash === h)) return 'Self-evolution apply denied: tool call is not part of the approved candidate action set.'
      const done = successfulActionHashes(config, exec, state)
      const next = state.stagedActions.find(a => !done.has(a.actionHash))
      if (!next) return 'Self-evolution apply denied: every approved action already completed successfully.'
      if (next.tool !== exec.name || next.actionHash !== h) return 'Self-evolution apply denied: approved actions must execute in their sealed order.'
    }
    return reserveCall(config, exec, state, template, effect)
  })

  ctx.on('tools/result', (exec, result) => {
    let state
    try { state = readActive(config, exec) } catch { return }
    if (!state || state.closed) return
    try { verifiedTemplateForState(state) } catch { return }
    cleanupApprovedArtifacts(config, exec, state)
    let key; try { key = executionKey(exec) } catch { return }
    const pending = Array.isArray(state.pendingCalls) ? state.pendingCalls : []
    const reservation = pending.find(x => x.callKey === key); if (!reservation) return
    state.pendingCalls = pending.filter(x => x.callKey !== key)
    let returnedArgsHash = null; let returnedActionHash = null; try { returnedArgsHash = sha(exec.arguments); returnedActionHash = actionHash(exec.name, exec.arguments) } catch {}
    const bindingMismatch = reservation.tool !== exec.name || reservation.argsHash !== returnedArgsHash || reservation.actionHash !== returnedActionHash
    const row = {
      schemaVersion: 3, time: now(), runId: state.runId, nodeId: reservation.nodeId, tool: reservation.tool, effect: reservation.effect,
      actionHash: reservation.actionHash, argsHash: reservation.argsHash, isError: bindingMismatch || !!result.isError,
      resultHash: bindingMismatch ? shaText('tool-execution-binding-mismatch') : hashOpaque(result.isError ? result.error?.message ?? 'error' : result.value ?? result.content),
    }
    // Settle the admission reservation first. If receipt persistence fails afterwards,
    // the node lacks success evidence but the run remains abortable instead of stuck pending.
    state.toolCallCount = (state.toolCallCount ?? 0) + 1
    atomicJson(activePath(config, exec), state)
    appendFileSync(receiptsPath(config, exec), JSON.stringify(row) + '\n', { encoding: 'utf8', mode: 0o600 })
  })

  ctx.tools.register({
    name: 'graphlean_begin',
    description: 'Start a session-scoped governed graph. Selecting one optional node enables its connected optional branch bundle.',
    parameters: {
      type: 'object', additionalProperties: false,
      properties: {
        template_id: { type: 'string', minLength: 1, description: 'Canonical graph template id.' },
        optional_nodes: { type: 'array', items: { type: 'string', minLength: 1 }, description: 'Optional node ids; connected optional branches expand as a bundle.' },
      }, required: ['template_id'],
    },
    output: jsonOutput(),
    execute(args, exec) {
      validateBeginArgs(args); agentKey(exec)
      const all = templates(); const template = all.get(args.template_id); if (!template) throw new Error(`unknown GraphLean template: ${args.template_id}`)
      const existing = readActive(config, exec); if (existing && !existing.closed) throw new Error(`GraphLean run ${existing.runId} is already active for this agent`)
      const selected = normalizeSelectedOptional(template, args.optional_nodes)
      const selectedSet = new Set(selected)
      const activeNodes = template.nodes.filter(n => !n.optional || selectedSet.has(n.id)).map(n => n.id).sort()
      const skippedOptionalNodes = template.nodes.filter(n => n.optional && !selectedSet.has(n.id)).map(n => n.id).sort()
      const state = {
        schemaVersion: 3, runId: `run_${randomBytes(12).toString('hex')}`, templateId: template.template_id, templateHash: graphHash(template),
        currentNode: null, activeNodes, selectedOptionalNodes: selected, skippedOptionalNodes, completed: [], startedAt: now(), enteredAt: now(),
        candidateHash: null, candidateReviewHash: null, approvedCandidateHash: null, stagedActions: [], toolCallCount: 0, pendingCalls: [], closed: false,
      }
      const ready = readyNodes(template, state); if (ready.length === 0) throw new Error(`template ${args.template_id} has no executable root under the selected optional-node set`)
      state.currentNode = ready[0]
      atomicJson(activePath(config, exec), state); return safeState(state, template)
    },
  })

  ctx.tools.register({
    name: 'graphlean_status', description: 'Return this session\'s active GraphLean state; raw prompt/source/diff text is not stored.', parameters: { type: 'object', properties: {}, additionalProperties: false },
    output: jsonOutput(), execute(_args, exec) { validateNoArgs(_args); agentKey(exec); const state = readActive(config, exec); if (!state) return safeState(null); const template=verifiedTemplateForState(state); cleanupApprovedArtifacts(config,exec,state); return safeState(state,template) },
  })

  ctx.tools.register({
    name: 'graphlean_stage_candidate',
    description: 'Seal exact ordered workspace-write calls for human review before self-evolution apply.',
    parameters: {
      type: 'object', additionalProperties: false, required: ['actions'],
      properties: {
        actions: {
          type: 'array', minItems: 1, maxItems: 32,
          items: {
            type: 'object', additionalProperties: false, required: ['tool_name', 'arguments'],
            properties: { tool_name: { type: 'string', minLength: 1 }, arguments: {} },
          },
        },
      },
    },
    output: jsonOutput(),
    execute(args, exec) {
      validateStageArgs(args); const state = readActive(config, exec); if (!state || state.closed) throw new Error('no active GraphLean run')
      verifiedTemplateForState(state)
      if (state.templateId !== 'gt_self_evolution' || state.currentNode !== 'n_candidate') throw new Error('candidate actions can only be staged at gt_self_evolution/n_candidate')
      if (state.pendingCalls.length) throw new Error('candidate cannot be sealed while governed tool calls are pending')
      if (state.candidateHash !== null || state.stagedActions.length || state.candidateReviewHash !== null) throw new Error('candidate is already sealed for this run; abort/restart to stage a different candidate')
      if (!Array.isArray(args.actions) || args.actions.length < 1 || args.actions.length > 32) throw new Error('candidate requires 1..32 actions')
      const staged = []; const seen = new Set()
      for (const a of args.actions) {
        if (!a || typeof a.tool_name !== 'string' || !a.tool_name || CONTROL_TOOLS.has(a.tool_name) || TRANSPORT_TOOLS.has(a.tool_name)) throw new Error('candidate contains an invalid/control/transport tool')
        const effect = classify(a.tool_name, a.arguments, config)
        if (effect !== 'workspace_write') throw new Error(`candidate action ${a.tool_name} is ${effect}; only exact workspace_write actions may be staged`)
        if (!WORKSPACE_WRITE_TOOLS.has(a.tool_name) && a.tool_name !== 'str_replace_editor') throw new Error(`candidate action ${a.tool_name} is not a path-auditable built-in mutation tool`)
        const protectedReason = protectedAccessReason(a.tool_name, a.arguments, config, exec); if (protectedReason) throw new Error(protectedReason)
        const h = actionHash(a.tool_name, a.arguments); if (seen.has(h)) throw new Error('candidate contains a duplicate action')
        seen.add(h); staged.push({ tool: a.tool_name, actionHash: h })
      }
      const rawBytes = Buffer.byteLength(canonical(args.actions), 'utf8'); if (rawBytes > 1_048_576) throw new Error('candidate review payload exceeds 1 MiB')
      state.stagedActions = staged
      state.candidateHash = sha({ templateId: state.templateId, templateHash: state.templateHash, actions: staged })
      state.approvedCandidateHash = null; state.stagedAt = now()
      const reviewPath = candidateReviewPath(config, exec, state.runId)
      try {
        atomicJson(reviewPath, { schemaVersion: 1, runId: state.runId, candidateHash: state.candidateHash, actionHashes: staged.map(a => a.actionHash), actions: args.actions })
        state.candidateReviewHash = shaText(readFileSync(reviewPath, 'utf8'))
        atomicJson(activePath(config, exec), state)
      } catch (error) {
        safeUnlink(reviewPath); throw error
      }
      return { candidateHash: state.candidateHash, candidateReviewHash: state.candidateReviewHash, actionCount: staged.length, actionHashes: staged.map(a => a.actionHash), reviewStoredLocally: true }
    },
  })

  ctx.tools.register({
    name: 'graphlean_advance',
    description: 'Complete the current node and enter the next ready node; required receipts and approvals are enforced.',
    parameters: { type: 'object', properties: {}, additionalProperties: false }, output: jsonOutput(),
    execute(_args, exec) {
      validateNoArgs(_args); const state = readActive(config, exec); if (!state || state.closed) throw new Error('no active GraphLean run')
      const template = verifiedTemplateForState(state); if (runExpired(state, template)) throw new Error(`GraphLean run exceeded max_total_latency_ms=${template.budgets.max_total_latency_ms}; abort required`)
      const node = nodeById(template, state.currentNode)
      if (Array.isArray(state.pendingCalls) && state.pendingCalls.length) throw new Error(`cannot advance while ${state.pendingCalls.length} tool call(s) are still pending`)
      let approvalTokenPath = null; let candidateReviewToDelete = null
      if (node.type === 'approval') {
        const p = approvalPath(config, exec, state.runId); if (!existsSync(p)) throw new Error('manual approval token missing; use graphleanctl.py approve')
        const token = readJson(p); if (!isPlainObject(token) || Object.keys(token).sort().join(',') !== 'candidateHash,runId,schemaVersion' || token.schemaVersion !== 3 || token.runId !== state.runId || token.candidateHash !== state.candidateHash) throw new Error('approval token is not bound to this run/candidate')
        const reviewPath = candidateReviewPath(config, exec, state.runId); if (!existsSync(reviewPath) || shaText(readFileSync(reviewPath, 'utf8')) !== state.candidateReviewHash) throw new Error('candidate review packet changed after human approval; approval must be renewed')
        state.approvedCandidateHash = state.candidateHash; state.approvedAt = now(); approvalTokenPath = p; candidateReviewToDelete = reviewPath
      }
      if (state.templateId === 'gt_self_evolution' && state.currentNode === 'n_candidate') {
        if (!state.candidateHash || !Array.isArray(state.stagedActions) || state.stagedActions.length === 0) throw new Error('n_candidate cannot complete before exact candidate actions are staged')
        const reviewPath = candidateReviewPath(config, exec, state.runId); if (!existsSync(reviewPath)) throw new Error('n_candidate cannot complete before the local human review packet is durable')
        const reviewText = readFileSync(reviewPath, 'utf8'); if (shaText(reviewText) !== state.candidateReviewHash) throw new Error('candidate review packet hash mismatch'); const review = JSON.parse(reviewText); if (review.runId !== state.runId || review.candidateHash !== state.candidateHash || canonical(review.actionHashes) !== canonical(state.stagedActions.map(a => a.actionHash))) throw new Error('candidate review packet is not bound to staged actions')
      } else if (state.templateId === 'gt_self_evolution' && state.currentNode === 'n_apply') {
        if (state.approvedCandidateHash !== state.candidateHash) throw new Error('n_apply cannot complete without exact candidate approval')
        const done = successfulActionHashes(config, exec, state)
        const missing = state.stagedActions.filter(a => !done.has(a.actionHash))
        if (missing.length) throw new Error(`n_apply cannot complete; ${missing.length} approved action(s) lack successful receipts`)
      } else if (node.authority !== 'read_only' && !successfulReceiptSince(config, exec, state, node.authority)) {
        throw new Error(`node ${node.id} cannot complete before a successful ${node.authority} tool receipt`)
      }
      if (!state.completed.includes(node.id)) state.completed.push(node.id)
      const unfinished = state.activeNodes.filter(id => !state.completed.includes(id))
      if (unfinished.length === 0) {
        state.closed = true; state.enteredAt = now(); atomicJson(activePath(config, exec), state)
        if (approvalTokenPath) safeUnlink(approvalTokenPath)
        if (candidateReviewToDelete) safeUnlink(candidateReviewToDelete)
        return safeState(state, template)
      }
      const ready = readyNodes(template, state)
      if (ready.length === 0) throw new Error(`graph deadlock: unfinished nodes have no topologically ready node (${unfinished.join(', ')})`)
      state.currentNode = ready[0]; state.enteredAt = now(); atomicJson(activePath(config, exec), state)
      if (approvalTokenPath) safeUnlink(approvalTokenPath)
      if (candidateReviewToDelete) safeUnlink(candidateReviewToDelete)
      return safeState(state, template)
    },
  })

  ctx.tools.register({
    name: 'graphlean_abort',
    description: "Abort the active graph; denied while governed tool calls are pending.",
    parameters: { type: 'object', properties: {}, additionalProperties: false }, output: jsonOutput(),
    execute(_args, exec) {
      validateNoArgs(_args); const state = readActive(config, exec); if (!state || state.closed) throw new Error('no active GraphLean run')
      verifiedTemplateForState(state); if (state.pendingCalls.length) throw new Error(`cannot abort while ${state.pendingCalls.length} tool call(s) are pending`)
      safeUnlink(candidateReviewPath(config, exec, state.runId)); safeUnlink(approvalPath(config, exec, state.runId)); safeUnlink(activePath(config, exec))
      return { aborted: true, runId: state.runId, templateId: state.templateId, completedNodeCount: state.completed.length }
    },
  })

}
