import { apply } from '../dsh/index.js'
import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)))
const defs = []
const events = []
const promptSections = []
let guards = 0
const ctx = {
  tools: {
    register(def) { defs.push(def) },
    guard(_fn) { guards += 1 },
  },
  systemPrompt: {
    section(def) { promptSections.push(def); return () => {} },
  },
  on(name, _fn) { events.push(name) },
}
apply(ctx, {})

// DSH ToolSchema sends name + description + parameters to the model. Tool output
// schemas are host/runtime metadata and are deliberately excluded from wire bytes.
const visible = defs.map(({name, description, parameters}) => ({name, description, parameters}))
const modelVisibleJsonBytes = Buffer.byteLength(JSON.stringify(visible), 'utf8')
const systemPromptPolicyInjectionBytes = promptSections.reduce((n, section) => {
  const text = typeof section?.text === 'string' ? section.text : ''
  return n + Buffer.byteLength(text, 'utf8')
}, 0)
const graphFiles = [
  ...readdirSync(join(ROOT, 'graph', 'templates')).filter(x => x.endsWith('.json')).map(x => join(ROOT, 'graph', 'templates', x)),
  join(ROOT, 'graph', 'quality', 'quality-improvement.json'),
  join(ROOT, 'graph', 'evolution', 'self-evolution.json'),
]
const hostGraphPayloadBytes = graphFiles.reduce((n, p) => n + readFileSync(p).byteLength, 0)
const result = {
  schemaVersion: 2,
  product: 'GraphLean',
  version: '1.0.1',
  modelVisibleControlTools: visible.length,
  modelVisibleJsonBytes,
  hostGraphTemplates: graphFiles.length,
  hostGraphPayloadBytes,
  systemPromptPolicyInjectionBytes,
  registeredSystemPromptSections: promptSections.length,
  registeredHostGuards: guards,
  registeredHostEvents: [...events].sort(),
  note: 'Wire byte count follows DSH ToolSchema (name, description, parameters). Prompt bytes are instrumented from GraphLean systemPrompt.section registrations. Counts exclude DSH base tools, history and provider framing.'
}
process.stdout.write(JSON.stringify(result, null, 2) + '\n')
